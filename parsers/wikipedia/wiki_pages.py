import re
import time
from selenium.webdriver.support.ui import WebDriverWait
import pandas as pd
from src.config import ENGINE
from datetime import datetime
from dateutil import parser
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from src.sql_utils import execute_delete_query
from parsers.utils import skip
from parsers.wikipedia.custom_func import *
from parsers.wikipedia.wiki_utils import _read_wiki_tables, split_destinations, unify_symbols, clearify_airport_name, remove_link

now = datetime.now()


class WikiAirportPage():
    def __init__(self, link: str, driver: WebDriver):
        self.driver = driver
        self.driver.get(link)
        if 'Hart' in link:
            self.custom_fn = atl
        else:
            self.custom_fn = None
        self.TABLE_BASE_HREF = '//table[@class="wikitable sortable jquery-tablesorter"][1]'
        self.passenger_index = 0
        self.charter_index = None
        self.airline_index = 0
        self.destionation_index = 1
        self._reflected = False
        self.fallback_fns = (pittsburgh_legacy,)


    def reflect(self):
        # Navigation may finish before Wikipedia's tables appear. Inspect the
        # original HTML rather than Selenium .text (which omits hidden content).
        WebDriverWait(self.driver, 30).until(
            lambda driver: driver.execute_script('return document.readyState') == 'complete'
        )
        self._legacy_concourse_layout = has_legacy_concourse_layout(self.driver.page_source)
        # The generic table reader cannot attribute nested operator lists.
        # Reject the entire unsupported layout rather than return partial data.
        self._table_rows = ([] if self._legacy_concourse_layout
                            else _read_wiki_tables(self.driver.page_source))
        self.page_contains_table = bool(self._table_rows)
        self.charter_index = None
        self._reflected = True

    def mark_seasonal_flights(self, df: pd.DataFrame) -> pd.DataFrame:
        """Записывает в колонку признак сезонности направления

        Args:
            df (pd.DataFrame): _description_

        Returns:
            pd.DataFrame: _description_
        """
        for index, row in df.iterrows():
            if index == 0:
                continue
            airlines_are_equal = df.loc[index, 'airline'] == df.loc[index - 1, 'airline']
            destination_letter_is_less = df.loc[index, 'destination'] > df.loc[index - 1, 'destination']
            is_seasonal =  df.loc[index - 1, 'remark'] == 'Seasonal'
            is_charter = df.loc[index - 1, 'remark'] == 'Charter'
            if airlines_are_equal and destination_letter_is_less and (is_seasonal or is_charter):
                df.loc[index, 'remark'] = 'Seasonal' if is_seasonal else 'Charter'

        return df
    
    
    def mark_suspended_flights(self, df: pd.DataFrame) -> pd.DataFrame:
        """Записывает в колонку признак того, что направление приостановлено

        Args:
            df (pd.DataFrame): _description_

        Returns:
            pd.DataFrame: _description_
        """
        length = len(df.index)
        for idx, row in df.iterrows():
            opposite_index = length - (idx + 1)
            if opposite_index + 1 == length:
                continue
            #Looping backward
            airlines_are_equal = df.loc[opposite_index, 'airline'] == df.loc[opposite_index + 1, 'airline']
            #логичнее искать паттерн uspended, но и так тоже сойдёт
            is_suspended =  (df.loc[opposite_index + 1, 'remark'] or '') in ('all suspended', 'all flights suspended', 'Suspended+')
            both_suspended =  (df.loc[opposite_index + 1, 'remark'] or '') == 'both suspended'
            if airlines_are_equal and is_suspended:
                df.loc[opposite_index, 'remark'] = 'Suspended+'
            elif airlines_are_equal and both_suspended:
                df.loc[opposite_index, 'remark'] = 'Suspended++'

        return df 
        

    def remove_unnessesary_flights(self, df: pd.DataFrame) -> pd.DataFrame:
        """Удаляет ненужные (закрытые или неначатые) направления из таблицы

        Args:
            df (pd.DataFrame): _description_

        Returns:
            pd.DataFrame: _description_
        """
        df['sign'] = df['remark'].apply(lambda x: 
            'begin' in (x or '').lower() or 'start' in (x or '').lower() or 'from' in (x or '').lower() 
            or 'resume' in (x or '').lower() or 'suspended' in (x or '').lower())
        df = df.query("sign == False")
        return df.drop(columns=['sign'])


    def _purified(self, df: pd.DataFrame) -> pd.DataFrame:
        """Одна функция, которая очищает весь датафрейм от нежелательных элементов
        """
        if self.page_contains_table and not df.empty:
            df = self.mark_suspended_flights(df)
        if len(df) == 0:
            return df

        df['destination'] = df['destination'].apply(lambda x: unify_symbols(x))
        df = self.remove_unnessesary_flights(df)
        df = df.replace({"destination": replacement_dict})
        
        #if destination contains number or is empty: remove
        df['sign'] = df['destination'].apply(lambda x: not bool(x.strip()) if isinstance(x, str) else True)
        df = df.query("sign == False")
        df['airline'] = df['airline'].apply(lambda x: x.split("operated by")[1].strip() if "operated by" in x else x)
        #if airline is cargo: remove
        df['sign'] = df['airline'].apply(lambda x: x in cargo_airlines['airline'].to_list())
        df = df.query("sign == False")

        #remove empty deastinations
        
        black_list = ('official site', 'requires Adobe Flash', 'Official website', 'English', 'Russian', 'official website')
        df = df.query("destination not in @black_list")
        return df.drop(columns=['sign'])

    @staticmethod
    def _airl_and_dest_to_df(airlines: list, destinations: list) -> pd.DataFrame:
        """Принимает на вход списки авиакомпаний и направлений и превращает их в таблицу рейсов

        Args:
            airlines (list): _description_
            destinations (list): _description_

        Returns:
            pd.DataFrame: _description_
        """

        if len(airlines) != len(destinations):
            raise ValueError("Airline and destination row counts differ")
        records = []
        for airline, text in zip(airlines, destinations):
            group = None
            for airport in split_destinations(text):
                match = re.match(r'^(Seasonal charter|Seasonal|Charter|Hajj)\s*:\s*', airport, re.I)
                if match:
                    group = match.group(1).title()
                    airport = airport[match.end():]
                if not airport:
                    continue
                destination, remark = clearify_airport_name(airport)
                destination = remove_link(destination).strip(' *')
                if destination:
                    records.append(dict(airline=remove_link(airline),
                                        destination=destination, remark=remark or group))
        return pd.DataFrame.from_records(records, columns=['airline', 'destination', 'remark'])


    def get_passenger_flights(self, custom_fn=None):
        if not self._reflected:
            self.reflect()
        if custom_fn is not None:
            airlines, destinations = custom_fn(self.driver)
        elif self._legacy_concourse_layout:
            return pd.DataFrame(columns=['airline', 'destination', 'remark'])
        elif self.page_contains_table:
            rows = [r for r in self._table_rows if not r['charter']]
            airlines = [r['airline'] for r in rows]
            destinations = [r['destinations'] for r in rows]
        else:
            elements = [el.text for el in self.driver.find_elements(By.XPATH, '//div[@class="mw-content-ltr mw-parser-output"]/ul/li')]
            #elements = self.driver.find_element(By.XPATH, '//div[@class="mw-heading mw-heading2"]/following-sibling::ul').text.split("\n")
            airlines, destinations = [], []
            for el in elements:
                pairs = el.split(" (")
                if len(pairs) > 1:
                    airlines.append(pairs[0])
                    destinations.append(pairs[1])

        df = self._airl_and_dest_to_df(airlines, destinations)
        return self._purified(df)
                    
            
    def get_charter_flights(self):
        if not self._reflected:
            self.reflect()
        rows = [r for r in getattr(self, '_table_rows', []) if r['charter']]
        if not rows:
            return pd.DataFrame(columns=['airline', 'destination', 'remark'])
        airlines = [r['airline'] for r in rows]
        destinations = [r['destinations'] for r in rows]

        df = self._airl_and_dest_to_df(airlines, destinations)
        df = self._purified(df)
        df['remark'] = 'Charter'
        return df          

    def get_flights(self, custom_fn=None):
        
        if not self._reflected:
            self.reflect()
        passenger = self.get_passenger_flights(custom_fn if custom_fn is not None else self.custom_fn)
        charter = self.get_charter_flights()

        result = pd.concat([passenger, charter], ignore_index=True)
        # Only zero usable destinations triggers a fallback. Do not merge
        # competing parsers or iterate through the old custom handlers.
        if result.empty:
            for fallback in self.fallback_fns:
                result = self.get_passenger_flights(custom_fn=fallback)
                if not result.empty:
                    break
        return result.drop_duplicates().reset_index(drop=True)


class WikiAirport():
    def __init__(self, code: str, driver: WebDriver):
        self.code = code
        self.driver = driver
        self.links = []


    def __repr__(self):
        return f'WikiAirport(code={self.code})'


    def _get_links_from_single_page(self):
        date_links = []
        links = self.driver.find_elements(By.XPATH, '//a[@class="mw-changeslist-date"]')
        for el in links:
            date = parser.parse(el.text)
            date_links.append({
                'link': el.get_attribute('href'), 
                'date': date.date(),
                'year': date.year,
                'month': date.month,
            })
        return date_links


    def _get_historic_dates(self):
        date_links = self._get_links_from_single_page()
        while True:
            try:
                link = self.driver.find_element(By.XPATH, '//a[@class="mw-prevlink"]')
                self.driver.get(link.get_attribute('href'))
                time.sleep(1.3)
                date_links += self._get_links_from_single_page()
            except (NoSuchElementException, StaleElementReferenceException) as e:
                break
    
        df = pd.DataFrame.from_records(date_links)
        df = df.groupby(['year', 'month']).first().query("month == 5")
        self.links = df.to_dict(orient="records")


    def _save_historic_links(self, drop_previous_links=False):
        df = pd.DataFrame.from_records(self.links)[['link', 'date']]
        df['iata'] = self.code
        if drop_previous_links:
            res = execute_delete_query(f"""delete from wikipedia.links where iata = '{self.code}'""")
        df.to_sql('links', ENGINE, schema="wikipedia", if_exists='append', index=False)
        print(f'Исторические ссылки сохранены для {self.code}')

    
    def _get_specific_dates(self, dates: list) -> list:
        """По списку годов получается ссылки на страницы википедии

        Args:
            dates (list): список годов

        Returns:
            list: {date: datetime.date, link: str}[]
        """
        date_links = self._get_links_from_single_page()
        while True:
            try:
                link = self.driver.find_element(By.XPATH, '//a[@class="mw-prevlink"]')
                self.driver.get(link.get_attribute('href'))
                time.sleep(2)
                date_links += self._get_links_from_single_page()
            except (NoSuchElementException, StaleElementReferenceException) as e:
                break
        df = pd.DataFrame.from_records(date_links)
        if len(df) == 0:
            return []
        links = []
        for date in dates:
            a = df.query("year == %s and month == 5" % (date))[["date", "link"]]
            if len(a) > 1:
                links.append(a.iloc[1].to_dict())
            else:
                a = df.query("year == %s and month == 6" % (date))[["date", "link"]]
                if len(a) > 0:
                    links.append(a.iloc[0].to_dict())
                else:
                    a = df.query("year == %s and month == 7" % (date))[["date", "link"]]
                    if len(a) > 0:
                        links.append(a.iloc[0].to_dict())
        return links

    @skip((ValueError, KeyError), expects=pd.DataFrame())
    def get_historic_flights(self, wiki_link: str) -> pd.DataFrame:
        """Возвразает DataFrame со всеми авиакомпаниями и направлениями по данному аэропорту за весь временной ряд.

        Args:
            wiki_link (str): Ссылка на текущую статью об аэропорте

        Returns:
            pd.DataFrame: _description_
        """
        retro_link = wiki_link.replace('/wiki/', '/w/index.php?title=') + '&action=history&dir=prev&limit=100'
        self.driver.get(retro_link)
        time.sleep(2)
        #зашёл на страницу, прошёл в историю
        #получил нужные временные срезы
        self._get_historic_dates()
        self._save_historic_links(drop_previous_links=True)
        frames = []
        for el in self.links:
            page = WikiAirportPage(el['link'], self.driver)
            page.reflect()
            df = page.get_flights()
            df['date'] = el['date']
            df['origin'] = self.code
            frames.append(df)
        return pd.concat(frames)

