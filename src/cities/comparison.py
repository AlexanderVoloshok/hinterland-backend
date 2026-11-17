from sqlalchemy import text
from src.sql_utils import read_sql


def get_centroid_mobility_chart_data():
    df = read_sql("""SELECT * FROM wikipedia.centroid_migrations_cache""")
    df["airport_name_ru"] = df["airport_name_ru"].fillna('')
    return df.to_dict(orient="records")

RANKING_REGIONS = {
    "Asia", "South America", "North America", "Africa", "Russia", "Europe",
}
RANKING_COLUMNS = {"position", "ru_name", "hinterland_size", "rank_up", "size_up"}

HINTERLAND_RANKING_SQL = text("""
    SELECT r.city_id, r.city, r.ru_name, r.flag, r.position AS rank,  r.position, r.hinterland_size, r.rank_up, r.size_up
    FROM wikipedia.get_hinterland_ranking(:year, :region, :order_by, :direction) WITH ORDINALITY AS r
    ORDER BY r.ordinality
""")


def get_hinterlands_sizes(year: int, region: str | None = None, order_by: str = "position", direction: str = "asc") -> list[dict]:
    region = region or None
    direction = direction

    df = read_sql(HINTERLAND_RANKING_SQL, {
        "year": year,
        "region": region,
        "order_by": order_by,
        "direction": direction.lower(),
    })
    df["ru_name"] = df["ru_name"].fillna("")
    return df.to_dict(orient="records")
