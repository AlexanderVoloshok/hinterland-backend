import os
import pandas as pd
from src.config import CONFIG, ENGINE
from src.sql_utils import execute_delete_query


def remove_cargo_airlines():
    airports = pd.read_sql("""
        select origin, count(destination) from wikipedia.airlines_and_destinations
        where airline in ('TNT', 'UPS', 'FedEx') or airline like '%%Cargo'
        group by origin
        order by count desc
    """, ENGINE).origin.values
    res = execute_delete_query("""
        delete from wikipedia.airlines_and_destinations
        where airline in ('TNT', 'UPS', 'FedEx') or airline like '%%Cargo'
    """)
    print(res)

    #TODO: достаточно просто обновить файл в completed
    for code in airports:
        df = pd.read_sql(f"select * from wikipedia.airlines_and_destinations where origin = '{code}'", ENGINE)
        if os.path.exists(f"{CONFIG.FOLDER}/parsers/wikipedia/completed/{code}.xlsx"):
            df.to_excel(f"{CONFIG.FOLDER}/parsers/wikipedia/completed/{code}.xlsx")
        elif os.path.exists(f"{CONFIG.FOLDER}/parsers/wikipedia/completed/{code}_new.xlsx"):
            df.to_excel(f"{CONFIG.FOLDER}/parsers/wikipedia/completed/{code}_new.xlsx")
        else:
            print(f'work on {code} is not finished yet')