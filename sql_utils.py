import pandas as pd
import geopandas as gpd
from config import ENGINE

def read_sql(query: str, params: tuple = ()):
    with ENGINE.connect() as conn:
        try:
            df = pd.read_sql(query, ENGINE, params=params)
            return df
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()


def read_postgis(query: str, params: tuple = (), **kwargs):
    geom_col = kwargs.get('geom_col', 'geom')
    with ENGINE.connect() as conn:
        try:
            df = gpd.read_postgis(query, ENGINE, params=params, geom_col=geom_col)  
            return df
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()


def execute_sql_query(query):
    with ENGINE.begin() as conn:
        try:
           result = conn.execute(query)
           return result
        except Exception as e:
            raise e
        finally:
            if conn:
                conn.close()


def execute_sql_and_commit(queries, payload: dict = None):
    with ENGINE.connect() as conn:
        with conn.begin() as trans:
            try:
                if not isinstance(queries, list):
                    queries = [queries]
                for q in queries:
                    if payload is not None:
                        result = conn.execute(q, payload)
                    else:
                        result = conn.execute(q)
                trans.commit()
                return result
            except Exception as e:
                raise e
            finally:
                if conn:
                    conn.close()