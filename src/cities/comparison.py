from src.sql_utils import read_sql


def get_centroid_mobility_chart_data():
    df = read_sql("""SELECT * FROM wikipedia.centroid_migrations""")
    df["airport_name_ru"] = df["airport_name_ru"].fillna('')
    return df.to_dict(orient="records")


def get_hinterlands_sizes(year):
    df = read_sql("""
        SELECT *, city as city_name_ru, 'ru' as flag, -1 as rank_up, 1 as size_up FROM wikipedia.hinterland_size_dynamics
        WHERE year = %s
        ORDER BY hinterland_size desc
        limit 30
    """ % year)
    df["city_name_ru"] = df["city_name_ru"].fillna('')
    return df.to_dict(orient="records")