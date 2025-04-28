import pandas as pd
import json
from sql_utils import read_sql, read_postgis


def prepare_cities_structure(table: pd.DataFrame):
    countries = table['country_name_ru'].unique()
    d = []
    for country in countries:
        cities = table.query("country_name_ru == '%s'" %country).reset_index()
        d.append({
            "country_name_ru": country,
            "country_code": cities.loc[0, 'country_code'],
            "cities_count": len(cities),
            "children": json.loads(cities.to_json(orient="records"))
        })
    return sorted(d, key=lambda x: x['country_name_ru'])


def get_cities_list():
    table = read_sql("""
        SELECT country_name_ru, city, country_code, airport_name_ru, ST_X(geometry) as x, ST_Y(geometry) as y FROM wikipedia.cities_available
        ORDER BY airport_name_ru
    """)
    return prepare_cities_structure(table)


class City:
    def __init__(self, name: str) -> None:
        self.name = name


    def get_hinterland_numbers(self):
        df = read_sql("""
            select year, hinterland_size::integer as value, year::integer as name from wikipedia.hinterland_size_dynamics
            where city = '%s' and season = 'summer'
            order by year desc
        """ % self.name)
        a = df['value'].idxmin()
        c = df['value'].idxmax()
        current = df.loc[0]
        l = read_sql("""
            SELECT date, city_from, min(round) AS min, max(round) AS max FROM wikipedia.routes_length
            where city_from = '%s'
            GROUP BY date, city_from
            ORDER BY date desc;
        """ % self.name)
        return {
            'current': int(current['value']),
            'min_size': int(df.loc[a, 'value']),
            'min_label': int(df.loc[a, 'name']),
            'max_size': int(df.loc[c, 'value']),
            'max_label': int(df.loc[c, 'name']),
            'min_length': l['min'].to_list()[0],
            'max_length': l['max'].to_list()[0]
        }


    def get_hinterland_dynamics(self, arrg_type: str):
        df = read_sql("""
            select hinterland_size as value, year::text as name from wikipedia.hinterland_size_dynamics
            where city = '%s' and season = 'summer'
        """ % self.name)
        return df.to_dict(orient="records")


    def hinterland_map(self):
        df = read_sql("""
            select * from wikipedia.hinterland_dynamic_for_map
            where city_from = '%s'
        """ % self.name)
        result = {str(int(row['date'])): row['json_build_object'] for index, row in df.iterrows()}
        return result


    def get_hinterland_changes(self, year_from: int, year_to: int):
        df = read_sql("""
            select * from wikipedia.city_dates_changes('%s', %s, %s)
            where destination is not null
        """ % (self.name, year_from, year_to))
        return df.to_dict(orient="records")


    def get_route_timeline(self, destinations: tuple):
        df = read_sql("""
            select airport_name_ru, city_to, country_code, array_agg(date) as dates from wikipedia.hinterlands
            where city_from = '%s' and city_to in ('%s')
            group by city_to, country_code, airport_name_ru
        """ % (self.name, "', '".join(destinations)))
        return df.to_dict(orient="records")


    def get_min_max_route_length_dynamics(self):
        df = read_sql("""
            SELECT date::text, city_from, min(round) AS min, max(round) AS max FROM wikipedia.routes_length
            where city_from = '%s'
            GROUP BY date, city_from
            ORDER BY date;
        """ % self.name)
        results = [
            {"name": "Длиннейший маршрут", "series": []},
            {"name": "Кратчайший маршрут", "series": []}
        ]
        for index, row in df.iterrows():
            results[0]['series'].append({'name': row['date'], 'value': row['max']})
            results[1]['series'].append({'name': row['date'], 'value': row['min']})
        return results


    def get_route_length_distribution(self, year: int):
        df = read_sql("""
            select * from wikipedia.routes_length
            where city_from = '%s' and date = %s
        """ % (self.name, year))

        bins = pd.IntervalIndex.from_tuples([
            (0, 1000), (1000, 3000), (3000, 5000), (5000, 7000), (7000, 10000), (10000, 40000)
        ])
        result = pd.cut(df['round'], bins).value_counts().sort_index()
        labels = {
            '(0, 1000]': 'Менее 1 тыс.км', '(1000, 3000]': '1-3 тыс.км', '(3000, 5000]': '3-5 тыс.км', '(5000, 7000]': '5-7 тыс.км', '(7000, 10000]': '7-10 тыс.км', '(10000, 40000]': 'Более 10 тыс.км'
        }
        return [{'name':labels[str(k)], 'value': v} for k,v in result.items()]


    def centroid_migration(self):
        df = read_postgis("""
            select * from wikipedia.hinterland_centroids
            where city_from = %s
        """, params=(self.name,), geom_col="geometry")
        return json.loads(df.to_json())


    def destinations_list(self):
        table = read_sql("""select city_to as city, airport_name_ru, country_code, country_name_ru from wikipedia.hinterlands
            where city_from = '%s'
            group by city_to, airport_name_ru, country_code, country_name_ru""" % self.name)
        return prepare_cities_structure(table)


    def airlines_list(self):
        df = read_sql("""
            select ad.airline, airls.color, airls.is_lowcost FROM wikipedia.airlines_and_destinations ad
            join (
            	SELECT airport_name, iata, city FROM flightradar24.airports WHERE link IS NOT NULL
            ) sample on ad.origin = sample.iata
            join flightradar24.airlines airls on ad.airline = airls.airline
            where city = '%s'
            group by ad.airline, airls.color, airls.is_lowcost
        """ % self.name)
        d = {}
        for _, row in df.iterrows():
            d[row['airline']] = {'color': row['color'], 'is_lowcost': row['is_lowcost']}
        return d

    @property
    def wiki_links(self):
        query = """
            SELECT date_part('year'::text, links.date):: text as year, links.date, links.iata, links.link FROM wikipedia.links
            LEFT JOIN flightradar24.airports ON links.iata = airports.iata
            where airports.city = '%s'
            group by airports.city, links.date, links.iata, links.link
            order by airports.city, links.date
        """ % self.name

        df = read_sql(query)
        d = {row['year']:[] for index, row in df.iterrows()}
        for index, row in df.iterrows():
            d[row['year']].append({ 'code': row['iata'], 'date': row['date'], 'link': row['link'] })

        return d
