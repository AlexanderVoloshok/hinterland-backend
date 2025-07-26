import pandas as pd
import json
from typing import Union
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


    def get_hinterland_dynamics(self, arrg_type: str, airline: Union[str, None] = None):
        if arrg_type == 'airline':
            q = """
                WITH destination_airlines AS (
                    SELECT date_part('year'::text, date) as date, destination, ARRAY_AGG(DISTINCT airline) AS airlines FROM wikipedia.airlines_and_destinations
                	where origin in (
                		select iata from flightradar24.airports
                		where city = '%s'
                		group by iata
                	)
                    GROUP BY date, destination
                ),
                airlines_list AS (
                    SELECT airline FROM wikipedia.airlines_and_destinations
                	group by airline
                ),
                combinations AS (
                    SELECT da.date, al.airline AS target_airline, da.destination, da.airlines FROM destination_airlines da
                    CROSS JOIN airlines_list al
                )
                SELECT date, target_airline,
                    COUNT(DISTINCT CASE 
                        WHEN airlines = ARRAY[target_airline] THEN destination
                    END) AS only_target_airline,
                    COUNT(DISTINCT CASE 
                        WHEN target_airline = ANY(airlines) AND CARDINALITY(airlines) > 1 THEN destination
                    END) AS shared_destinations,
                    COUNT(DISTINCT CASE 
                        WHEN NOT target_airline = ANY(airlines) THEN destination
                    END) AS no_flights
                FROM combinations
                where target_airline = '%s'
                GROUP BY date, target_airline
                ORDER BY date, target_airline;
            """ % (self.name, airline.replace("%20", ""))
        elif arrg_type == 'lcc':
            q = """
                WITH destinations_by_cost AS (
                  SELECT date, destination, bool_or(is_lowcost) AS has_true, bool_or(NOT is_lowcost) AS has_false
                  FROM (
                  	select date_part('year'::text, date) as date, destination, is_lowcost from wikipedia.lcc_continent
                	where origin in (
                		select iata from flightradar24.airports
                		where city = '%s'
                		group by iata
                    )
                  ) tbl
                  GROUP BY date, destination
                ),
                classified AS (
                  SELECT
                    date,
                    CASE
                      WHEN has_true AND NOT has_false THEN 'only_true'
                      WHEN NOT has_true AND has_false THEN 'only_false'
                      WHEN has_true AND has_false THEN 'both'
                    END AS cost_category
                  FROM destinations_by_cost
                )
                SELECT
                  date,
                  COUNT(*) FILTER (WHERE cost_category = 'only_true') AS lcc,
                  COUNT(*) FILTER (WHERE cost_category = 'only_false') AS classic,
                  COUNT(*) FILTER (WHERE cost_category = 'both') AS both
                FROM classified
                GROUP BY date
                ORDER BY date;
            """ % self.name
        elif arrg_type == 'continent':
            q = """
                select date_part('year'::text, date) as date, continent, count(date) from wikipedia.lcc_continent
	            where origin in (
	            	(
                    	select iata from flightradar24.airports
                    	where city = '%s'
                    	group by iata
                    )
	            )
	            group by date_part('year'::text, date) , continent
            """ % self.name
        elif arrg_type == 'domestic':
            country = read_sql("SELECT country FROM flightradar24.airports WHERE city = '%s' LIMIT 1" % self.name)
            q = """
                select date, line_type, count(line_type) from (
                    select * from (
                  	    select date_part('year'::text, date) as date, destination, 
                  	    case country 
                  	    	when '%s' then 'domestic'
                  	    	else 'international'
                  	    end as "line_type"
                  	    from wikipedia.lcc_continent
                	    where origin in (
                	    	(
                            	select iata from flightradar24.airports
                            	where city = '%s'
                            	group by iata
                            )
                	    )
                    )a group by date, destination, line_type
                )a group by date, line_type
            """ % (country['country'].values[0], self.name)
        else:
            q = """
            select hinterland_size as value, year::text as name from wikipedia.hinterland_size_dynamics
            where city = '%s' and season = 'summer'
        """ % self.name
        df = read_sql(q)

        if arrg_type in ('domestic', 'continent'):
            group_cols = [col for col in df.columns if col not in ['date', 'count']]
            df = df.pivot_table(
                index='date',   # строки — все, кроме date и count
                columns=group_cols[0],     # колонки — значения из date
                values='count',     # значения — count
                aggfunc='sum',      # агрегируем через сумму (можно менять)
                fill_value=0        # чтобы не было NaN
            ).reset_index()

            # Чтобы date-колонки не были вложенными
            df.columns.name = None

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


    def get_hinterland_structure(self, year: int = 2024, preset_name: str = None):
        #Для города (или страны/региона) имеется пресет - список тегов, по которым можно однозначно классифицировать города. У одного города в рамках одного пресетав не может быть двух тегов 
        if not preset_name:
            preset = read_sql("select tags from wikipedia.presets where city = '%s'" % self.name)
        else:
            preset = read_sql("select tags from wikipedia.presets where preset_name = '%s'" % preset_name)
        
        tags_str = "', '".join(preset.loc[0, 'tags'])
        q = """
            SELECT name, count(*) as value
            FROM (
              SELECT 
                (
                  SELECT tag FROM unnest(tags) AS tag
                  WHERE tag IN ('%s')
                  LIMIT 1
                ) AS name
              FROM wikipedia.hinterlands a
              WHERE city_from = '%s' AND date = %s
                AND tags && ARRAY['%s']
            ) matched
            GROUP BY name

            UNION ALL
            -- Подсчёт несовпавших тегов
            SELECT 'Прочие' AS name, count(*) as value
            FROM wikipedia.hinterlands a
            WHERE city_from = '%s' AND date = %s
              AND NOT (tags && ARRAY['%s'])

            ORDER BY value DESC;        
        """ % (tags_str, self.name, year, tags_str, self.name, year, tags_str)
        df = read_sql(q)
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
