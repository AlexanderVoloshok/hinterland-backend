from src.sql_utils import read_sql


SQL = """
WITH ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (
            PARTITION BY city_from ORDER BY year ASC
        ) AS rn_first,
        ROW_NUMBER() OVER (
            PARTITION BY city_from ORDER BY year DESC
        ) AS rn_last
    FROM wikipedia.hinterland_centroids c
    where year <= 2024
),
stats AS (
    SELECT
        a.airport_name_ru, 
        city_from,
        COUNT(*) AS point_count,
        MIN(year) AS first_year,
        MAX(year) AS last_year,
        ST_Extent(c.geometry) AS bbox
    FROM wikipedia.hinterland_centroids c
    join flightradar24.airports a on a.city = c.city_from
    where year <= 2024
    GROUP BY a.airport_name_ru, city_from
),
bounds AS (
    SELECT
        *,
        ST_XMin(bbox) AS xmin,
        ST_XMax(bbox) AS xmax,
        ST_YMin(bbox) AS ymin,
        ST_YMax(bbox) AS ymax
    FROM stats
)
SELECT
    b.airport_name_ru,
    b.point_count,
    b.first_year,
    b.last_year,

    -- Смещение от самого старого центроида к самому новому.
    ROUND(
        (ST_Distance(
            f.geometry::geography,
            l.geometry::geography
        ) / 1000.0)::numeric,
        2
    ) AS displacement_km,

    ROUND(
        degrees(ST_Azimuth(
            f.geometry::geography,
            l.geometry::geography
        ))::numeric,
        2
    ) AS azimuth_deg,

    -- Ширина: расстояние между западной и восточной
    -- границами на средней широте bounding box.
    ROUND(
        (ST_Distance(
            ST_SetSRID(
                ST_MakePoint(b.xmin, (b.ymin + b.ymax) / 2.0),
                4326
            )::geography,
            ST_SetSRID(
                ST_MakePoint(b.xmax, (b.ymin + b.ymax) / 2.0),
                4326
            )::geography
        ) / 1000.0)::numeric,
        2
    ) AS bbox_width_km,

    -- Высота: расстояние между южной и северной
    -- границами на среднем меридиане bounding box.
    ROUND(
        (ST_Distance(
            ST_SetSRID(
                ST_MakePoint((b.xmin + b.xmax) / 2.0, b.ymin),
                4326
            )::geography,
            ST_SetSRID(
                ST_MakePoint((b.xmin + b.xmax) / 2.0, b.ymax),
                4326
            )::geography
        ) / 1000.0)::numeric,
        2
    ) AS bbox_height_km

FROM bounds b
JOIN ranked f
    ON f.city_from = b.city_from AND f.rn_first = 1
JOIN ranked l
    ON l.city_from = b.city_from AND l.rn_last = 1
ORDER BY b.city_from;
"""


def get_centroid_mobility_chart_data():
    df = read_sql(SQL)
    return df.to_dict(orient="records")