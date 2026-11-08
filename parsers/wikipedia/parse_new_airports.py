
from src.config import CONFIG
from parsers.wikipedia.wiki_pages import WikiAirport
from parsers.utils import get_driver
from src.sql_utils import read_sql


def parse_new_airports(iata_codes: tuple):
    driver = get_driver()

    query = """
        select iata, link from flightradar24.airports where iata in %s and link is not null
    """ % str(iata_codes)
    airports = read_sql(query)
    for index, row in airports.iterrows():
        airport = WikiAirport(row['iata'], driver)
        frame = airport.get_historic_flights(row['link'])
        frame.to_excel(f"{CONFIG.LEGACY_PARSERS_ROOT}/parsers/wikipedia/{row['iata']}.xlsx")

    driver.quit()