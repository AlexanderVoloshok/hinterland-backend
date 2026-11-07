from sqlalchemy import text
from src.sql_utils import read_sql


def get_centroid_mobility_chart_data():
    df = read_sql("""SELECT * FROM wikipedia.centroid_migrations_v2""")
    df["airport_name_ru"] = df["airport_name_ru"].fillna('')
    return df.to_dict(orient="records")

#TODO: В функцию
#TODO: динамический контент, чтобы можно было на фронте сортировать и делалась актуальная выборка
HINTERLAND_RANKING_SQL = text("""
    WITH ranked AS (
        SELECT year, city, city_id, hinterland_size,
            ROW_NUMBER() OVER (
                PARTITION BY year
                ORDER BY hinterland_size DESC, city ASC
            ) AS position
        FROM wikipedia.hinterland_size_dynamics_v2
        WHERE year IN (:year, :previous_year)
          AND hinterland_size IS NOT NULL
    )
    select current.city_id, current.city, c.ru_name, LOWER(c.country_code) AS flag,
        current.position AS rank, current.hinterland_size, previous.position - current.position AS rank_up,
        current.hinterland_size - previous.hinterland_size AS size_up
    FROM ranked AS current
    JOIN ranked AS previous ON previous.city_id = current.city_id AND previous.year = :previous_year
    JOIN wikipedia.cities AS c ON c.id = current.city_id
    WHERE current.year = :year
    ORDER BY current.position
    LIMIT 30
""")


def get_hinterlands_sizes(year: int) -> list[dict]:
    params = {
        "year": year,
        "previous_year": year - 1,
    }

    df = read_sql(HINTERLAND_RANKING_SQL, params)
    df["ru_name"] = df["ru_name"].fillna('')
    return df.to_dict(orient="records")