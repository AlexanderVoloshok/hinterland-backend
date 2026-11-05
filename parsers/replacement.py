import pandas as pd
from src.sql_utils import read_sql


def get_replacement_dict(filename: str='replacement'):
    df = pd.read_excel(f"d:/Sasha/Самолёты/Flightradar24 project/parsers/wikipedia/{filename}.xlsx")#.dropna()
    d = {row['from']: row['to'] for index, row in df.iterrows() if str(row['to']) != 'nan'}
    return d

replacement_airports = get_replacement_dict()
replacement_airlines = get_replacement_dict('replacement_airline')
cargo_airlines = read_sql("""SELECT airline FROM flightradar24.airlines WHERE purpose = 'cargo'""")