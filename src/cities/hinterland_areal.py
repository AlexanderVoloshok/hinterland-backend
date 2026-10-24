import json
import numpy as np
import pandas as pd
import geopandas as gpd
from shapely.geometry import Polygon, LineString, Point, box, shape
from shapely.affinity import translate
from shapely.ops import unary_union, transform
from shapely import make_valid
from pyproj import Geod, CRS, Transformer

from src.config import ENGINE
from src.sql_utils import read_sql


def read_hinterland_points(value):
    """Поддерживает Point, MultiPoint, Feature и FeatureCollection."""
    if isinstance(value, (str, bytes)):
        value = json.loads(value)
   
    geometries = []

    def visit(obj):
        if not isinstance(obj, dict):
            raise ValueError('Ожидается объект GeoJSON')
        kind = obj.get('type')
        if kind == 'FeatureCollection':
            for feature in obj['features']:
                visit(feature)
        elif kind == 'Feature':
            visit(obj['geometry'])
        elif kind == 'GeometryCollection':
            for geometry in obj['geometries']:
                visit(geometry)
        elif kind in ('Point', 'MultiPoint'):
            geom = shape(obj)
            geometries.extend(list(geom.geoms) if kind == 'MultiPoint' else [geom])
        else:
            raise ValueError(f'Хинтерланд должен состоять из точек, получено: {kind}')

    visit(value)
    
    if not geometries or any(g.is_empty or not g.is_valid for g in geometries):
        print('GeoJSON пуст или содержит некорректные точки')
    
    return gpd.GeoDataFrame(geometry=geometries, crs='EPSG:4326')


def _polygon_parts(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    if hasattr(geometry, 'geoms'):
        return [p for child in geometry.geoms for p in _polygon_parts(child)]
    return []


def _local_projection(lon, lat):
    """Локальная проекция только для одного короткого участка маршрута."""
    return CRS.from_proj4(
        f'+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +no_defs'
    )


def _wrap_piece(geometry):
    """Разрезает полигон по ±180° и возвращает долготы в [-180, 180]."""
    parts = []
    left, bottom, right, top = geometry.bounds
    for k in range(int(np.floor((left + 180) / 360)),
                   int(np.floor((right + 180) / 360)) + 1):
        strip = box(-180 + 360*k, -90, 180 + 360*k, 90)
        cut = geometry.intersection(strip)
        parts.extend(translate(p, xoff=-360*k) for p in _polygon_parts(cut))
    return parts


def _unproject_buffer(buffered, metric_crs, reference_lon):
    """Переносит небольшой локальный буфер в WGS84 без линии через весь мир.

    Для буфера, содержащего полюс, замыкает контур по широте ±90°.
    """
    inverse = Transformer.from_crs(metric_crs, 'EPSG:4326', always_xy=True)
    forward = Transformer.from_crs('EPSG:4326', metric_crs, always_xy=True)
    converted = []
    for polygon in _polygon_parts(buffered):
        lon, lat = inverse.transform(*zip(*polygon.exterior.coords))
        lon = np.rad2deg(np.unwrap(np.deg2rad(lon)))
        lat = np.asarray(lat)
        lon += 360 * round((reference_lon - float(np.median(lon))) / 360)
        pole = None
        for candidate in (90, -90):
            px, py = forward.transform(reference_lon, candidate)
            if np.isfinite([px, py]).all() and polygon.covers(Point(px, py)):
                pole = candidate
                break
        ring = list(zip(lon, lat))
        if pole is not None:
            # В географических координатах полярный буфер замыкается
            # двумя меридианами и параллелью полюса, а не прямой хордой.
            ring += [(lon[-1], pole), (lon[0], pole)]
        geographic = make_valid(Polygon(ring))
        for part in _polygon_parts(geographic):
            converted.extend(_wrap_piece(part))
    return converted


def _buffer_route_chunk(coords, radius_m):
    """Буфер отрезка не длиннее ~1000 км в собственной проекции."""
    geod = Geod(ellps='WGS84')
    start, end = coords[0], coords[-1]
    midpoint = geod.npts(*start, *end, 1)[0]
    local_crs = _local_projection(*midpoint)
    forward = Transformer.from_crs('EPSG:4326', local_crs, always_xy=True)
    xy = [forward.transform(lon, lat) for lon, lat in coords]
    if not np.isfinite(np.asarray(xy)).all():
        raise ValueError('Не удалось спроецировать участок геодезического ребра')
    tube = LineString(xy).buffer(radius_m, quad_segs=24)
    return _unproject_buffer(tube, local_crs, midpoint[0])


def calculate_polygon(points, land, point_buffer_km=400, edge_buffer_km=300,
                      smoothing_km=100, step_km=100, max_edge_km=None):
    """Глобальный геодезический MST, локальные буферы, обрезка по суше.

    Каждое ребро делится на геодезические отрезки длиной не более ~1000 км;
    буфер каждого отрезка считается в своей проекции AEQD. Полигон
    разрезается по ±180° перед объединением и сохранением в EPSG:4326.
    max_edge_km: если задан, рёбра MST длиннее этого значения не создают
    соединительных буферов. Буферы всех исходных точек сохраняются.
    Земля должна быть корректным полигональным слоем с известным CRS.
    """
    if points.crs is None or land.crs is None:
        raise ValueError('У точек и маски суши должен быть задан CRS')
    
    if points.empty:
        return gpd.GeoDataFrame(geometry=[], crs='EPSG:4326')

    p = points.to_crs(4326)
    if (p.geometry.isna().any() or p.geometry.is_empty.any()
            or not p.geom_type.eq('Point').all()):
        raise ValueError('Ожидаются непустые точечные геометрии')
    xy = np.unique(np.array([(g.x, g.y) for g in p.geometry]), axis=0)
    if not np.isfinite(xy).all() or (np.abs(xy[:, 1]) > 90).any():
        print('Некорректные географические координаты точек')
        return
    xy[:, 0] = (xy[:, 0] + 180) % 360 - 180
    xy = np.unique(xy, axis=0)
    geod = Geod(ellps='WGS84')
    n = len(xy)

    # MST Прима по расстояниям на эллипсоиде, без арифметического
    # усреднения долгот: +179° и -179° оказываются соседями.
    distances = np.zeros((n, n))
    for i in range(n):
        _, _, distances[i] = geod.inv(
            np.full(n, xy[i, 0]), np.full(n, xy[i, 1]), xy[:, 0], xy[:, 1]
        )
    used = np.zeros(n, dtype=bool)
    used[0] = True
    best = distances[0].copy()
    parent = np.zeros(n, dtype=int)
    edges = []
    for _ in range(n - 1):
        j = int(np.argmin(np.where(used, np.inf, best)))
        edges.append((int(parent[j]), j))
        used[j] = True
        update = (~used) & (distances[j] < best)
        best[update] = distances[j, update]
        parent[update] = j

    pieces = []
    disk = Point(0, 0).buffer(point_buffer_km * 1000, quad_segs=48)
    for lon, lat in xy:
        local_crs = _local_projection(lon, lat)
        pieces.extend(_unproject_buffer(disk, local_crs, lon))

    skipped_edges = 0
    for i, j in edges:
        if max_edge_km is not None and distances[i, j] > max_edge_km * 1000:
            skipped_edges += 1
            continue
        # Не проецируем весь маршрут сразу: даже противоположные точки
        # обрабатываются короткими участками вдоль кратчайшей геодезической.
        effective_step_km = min(step_km, 100)
        count = max(1, int(np.ceil(distances[i, j] / (effective_step_km * 1000))))
        intermediate = geod.npts(*xy[i], *xy[j], count - 1) if count > 1 else []
        route = [tuple(xy[i]), *intermediate,
                 tuple(xy[j])]
        chunk_size = max(1, int(1000 // effective_step_km))
        for start in range(0, count, chunk_size):
            pieces.extend(_buffer_route_chunk(
                route[start:min(start + chunk_size, count) + 1],
                edge_buffer_km * 1000
            ))

    if not pieces:
        result = gpd.GeoDataFrame(geometry=[], crs='EPSG:4326')
        result.attrs.update(mst_edges=len(edges), skipped_edges=skipped_edges,
                            unique_points=n, removed_parts=0)
        return result
    area = make_valid(unary_union(pieces))

    # Для небольших компонентов сохраняем исходное метрическое сглаживание.
    # Компоненты на шве и глобально протяжённые компоненты не сглаживаем:
    # отдельная метрическая проекция исказила бы их или раздвинула шов.
    if smoothing_km:
        smoothed = []
        for part in _polygon_parts(area):
            x0, y0, x1, y1 = part.bounds
            if (x1 - x0 < 100 and y1 - y0 < 100
                    and -85 < y0 <= y1 < 85
                    and x0 > -179.99 and x1 < 179.99):
                lon0, lat0 = (x0 + x1)/2, (y0 + y1)/2
                local_crs = _local_projection(lon0, lat0)
                forward = Transformer.from_crs('EPSG:4326', local_crs, always_xy=True)
                projected = transform(forward.transform, part)

                if np.isfinite(np.asarray(projected.bounds)).all():
                    closed = projected.buffer(smoothing_km * 1000).buffer(-smoothing_km * 1000)
                    smoothed.extend(_unproject_buffer(closed, local_crs, lon0))
                    continue

            smoothed.append(part)
            
        area = make_valid(unary_union(smoothed))

    # Заполняем отверстия ареала до пересечения с сушей. Отверстия самой
    # маски суши сохраняются (моря и озёра останутся незакрашенными).
    area = unary_union([Polygon(part.exterior) for part in _polygon_parts(area)])

    l = land.loc[land.geometry.notna() & ~land.geometry.is_empty].copy()
    land_parts = []
    for geom in l.geometry:
        if not np.isfinite(np.asarray(geom.bounds)).all():
            continue
        repaired = make_valid(geom)
        if repaired.intersects(area):
            land_parts.extend(_polygon_parts(repaired.intersection(area)))
    clipped = make_valid(unary_union(land_parts)) if land_parts else Polygon()

    # Точки на ±180° эквивалентны: проверяем обе координаты на шве.
    point_checks = [Point(lon, lat) for lon, lat in xy]
    point_checks += [Point(180 if lon == -180 else -180, lat)
                     for lon, lat in xy if abs(lon) == 180]
    point_union = unary_union(point_checks)
    all_parts = _polygon_parts(clipped)
    kept = [part for part in all_parts if part.intersects(point_union)]
    result = gpd.GeoDataFrame(geometry=kept, crs='EPSG:4326')
    result.attrs.update(mst_edges=len(edges), skipped_edges=skipped_edges,
                        unique_points=n,
                        removed_parts=len(all_parts)-len(kept))
    return result


def calculate_areals(city, years, data, max_edge_km=None):
    """Читает SQL один раз и фильтрует город и список years.

    Каждый год рассчитывается отдельно. Наложения ареалов темнее.
    polygon_alpha и point_alpha задают непрозрачность каждого среза.

    extent: (xmin, xmax, ymin, ymax) в map_crs. По умолчанию — охват точек
    и вычисленных полигонов с отступом. PNG/SVG определяются расширением файла.
    """
    
    export_layers = []
    for year in years:
        rows = data.loc[data['date'] == year]
        if len(rows) == 0 or year >= 2006:
            continue

        row = rows.iloc[0]
        points = read_hinterland_points(row['json_build_object'])
        polygon = calculate_polygon(points=points.copy(), land=countries, max_edge_km=max_edge_km)

        if polygon is not None:           
            if (polygon.geometry.isna().any() or polygon.geometry.is_empty.any()
                    or not polygon.geometry.is_valid.all()
                    or not polygon.geom_type.isin(['Polygon', 'MultiPolygon']).all()):
                print(f'{year}: вычисленный слой содержит некорректные полигоны')
            
            if not polygon.empty:
                export_polygon = polygon.to_crs("EPSG:4326").copy()
                export_polygon["city_id"] = 1
                export_polygon["city"] = city
                export_polygon["year"] = int(year)
                export_polygon["parameters_json"] = {
                    'max_edge_km': max_edge_km,
                    'point_buffer_km': 400, 
                    'edge_buffer_km':300,
                    'smoothing_km':100, 
                    'step_km':100
                }

                export_layers.append(export_polygon[["city_id", "city", "year", "geometry", "parameters_json"]])              

    if len(export_layers) > 0:
        all_areals = gpd.GeoDataFrame(
            pd.concat(export_layers, ignore_index=True),
            geometry="geometry",
            crs="EPSG:4326",
        )

        #TODO: параметры алгоритма сделать словарём или датаклассом в начале кода
        #TODO: удалять предыдущие версии ареалов

        all_areals.to_postgis('hinterland_areals', ENGINE, schema="wikipedia", if_exists='append', index=False)



if __name__ == '__main__':

    countries = gpd.read_file("d:/Sasha/Кандидатская/shp/ne_10m_admin_0_countries_lakes.shp")
    countries = countries.loc[countries.geometry.notna() & ~countries.geometry.is_empty]

    df = read_sql("""select * from wikipedia.hinterland_dynamic_for_map_v2""")

    cities = []
    years = []

    if len(cities) == 0:
        cities = df['city_from'].unique()
    
    for city in cities:
        city_rows = df.query("city_from == '%s'" % city).copy()
        city_rows['date'] = pd.to_numeric(city_rows['date'], errors='raise')

        if len(years) == 0:
            city_years = [int(d) for d in city_rows["date"].values]

        selected = city_rows.loc[city_rows['date'].isin(city_years)]
        
        calculate_areals(city, city_years, data=selected, max_edge_km=1000)
        print(city)