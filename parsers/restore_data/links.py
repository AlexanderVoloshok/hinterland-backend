import pandas as pd
import typing as ty
from src.config import ENGINE
from src.sql_utils import execute_delete_query


def update_links(data: ty.Union[dict, pd.DataFrame]):
    """Принимает на вход данные по аэропорту и заменяет ссылки на википедию в соответствии с данными
    """
    
    if isinstance(data, pd.DataFrame):
        elements = [row for index, row in data.iterrows()]
    else:
        elements = []
        for iata,links in data.items():
             for link_item in links:
                 link_item['iata'] = iata
                 elements.append(link_item)
        
    dicts = []
    for link_item in elements:
        res = execute_delete_query(f"""
            delete from wikipedia.links 
            where iata = '{link_item['iata']}' and date_part('month'::text, date) < 7 and date_part('year'::text, date) = {link_item['date'].year}
        """)
        dicts.append(link_item)
        print(res)

    df = pd.DataFrame.from_records(dicts)
    df.to_sql('links', ENGINE, schema="wikipedia", if_exists='append', index=False)