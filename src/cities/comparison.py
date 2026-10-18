from src.sql_utils import read_sql


def get_centroid_mobility_chart_data():
    df = read_sql("""SELECT * FROM wikipedia.centroid_migrations""")
    return df.to_dict(orient="records")