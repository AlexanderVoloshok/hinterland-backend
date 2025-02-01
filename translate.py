import pandas as pd
from psycopg2 import connect
from googletrans import Translator
from config import ENGINE, URI
translator = Translator()

df = pd.read_sql("""
    select city from flightradar24.airports 
    where city is not null and country = 'China'
    group by city
""", ENGINE)
l = [el for el in df['city'].to_list()]
print(len(df))
translations = translator.translate(l, origin="en", dest='ru')

conn = connect(URI)
with conn:
    with conn.cursor() as cursor:
        for x, trans in enumerate(translations):
            if "’" not in trans.text and "'" not in trans.text:
                cursor.execute("""
                    update flightradar24.airports set airport_name_ru = '%s' where city = '%s'
                """ % (trans.text, df.loc[x, 'city']))
                conn.commit()

            if x % 100 == 0:
                print(x)
cursor.close()
conn.close()
