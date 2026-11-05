import os
import re
import tempfile
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from sqlalchemy import bindparam, text
from parsers.wikipedia.wiki_pages import WikiAirportPage
from src.sql_utils import read_sql, execute_sql_and_commit, read_sql
from parsers.utils import get_driver

#TODO: на некоторых находимых страницах нужные разделы всё-таки есть

driver = None
COLUMNS = ['airline', 'destination', 'remark', 'date', 'origin']


def _codes(airports):
    if airports is None:
        return []
    if isinstance(airports, str):
        airports = [airports]
    return sorted({str(code).strip().upper() for code in airports})


def _query_links(airports, years=None, missing_only=False, match_by='date'):
    """The registry is the only source of expected snapshots."""

    conditions = ['l.link IS NOT NULL', "btrim(l.link) <> ''",
                  'l.date IS NOT NULL', 'l.iata IS NOT NULL']
    params = {}
    if _codes(airports):
        conditions.append('l.iata IN :airports')
        params['airports'] = _codes(airports)

    if years is not None:
        years = sorted({int(year) for year in years})
        if not years:
            return pd.DataFrame(columns=['iata', 'date', 'link'])
        conditions.append("extract(year FROM l.date)::integer IN :years")
        params['years'] = years

    if missing_only:
        same_date = ('d.date::date = l.date::date' if match_by == 'date' else
                     'extract(year FROM d.date) = extract(year FROM l.date)')
        conditions.append(f"""NOT EXISTS (
            SELECT 1 FROM wikipedia.airlines_and_destinations d
            WHERE d.origin = l.iata AND {same_date}
        )""")

    query = text("""
        SELECT DISTINCT l.iata, l.date::date AS date, l.link
        FROM wikipedia.links l
        WHERE l.link like '%%wikipedia%%' AND 
    """ + ' AND '.join(conditions) + ' ORDER BY l.iata, date, l.link')
    
    for key in params:
        query = query.bindparams(bindparam(key, expanding=True))

    return read_sql(query, params=params)


def _saved_paths(iata):
    base = Path('d:/Sasha/Самолёты/Flightradar24 project') / 'parsers' / 'wikipedia'
    return [base / folder / filename
            for folder in ('in progress', 'completed')
            for filename in (f'{iata}_new.xlsx', f'{iata}.xlsx')]


def _read_saved(iata):
    frames = []
    for path in _saved_paths(iata):
        if path.exists():
            frame = pd.read_excel(path)
            frame = frame.loc[:, ~frame.columns.astype(str).str.startswith('Unnamed:')]
            if 'origin' in frame:
                frame = frame.loc[frame['origin'].eq(iata)].copy()
            else:
                frame['origin'] = iata
            frames.append(frame)

    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


def _date_key(value, match_by):
    value = pd.Timestamp(value)
    return value.year if match_by == 'year' else value.date()


def get_missing_links(airports, source='db', match_by='date', include_staged=True):
    """Return registry links missing in DB or Excel.

    date: compare exact calendar dates; year: any snapshot in that year suffices.
    For source='db', include_staged also checks existing Excel output, so a
    rerun does not parse snapshots that have already been restored locally.
    No synthetic year ranges, month restrictions or airport exclusions apply.
    """
    if source not in ('db', 'file'):
        raise ValueError("source must be 'db' or 'file'")
    
    links = _query_links(airports, missing_only=source == 'db', match_by=match_by)
    if links.empty:
        return links
    
    if source == 'file' or include_staged:
        keep = pd.Series(True, index=links.index)
        for iata, group in links.groupby('iata'):
            saved = _read_saved(iata)
            dates = pd.to_datetime(saved['date'], errors='raise').dropna()
            existing = {_date_key(date, match_by) for date in dates}
            keep.loc[group.index] = [_date_key(date, match_by) not in existing for date in group['date']]
        links = links.loc[keep]

    return links.reset_index(drop=True)


def get_missing_dates_for_airport(iata, source='db', match_by='date', include_staged=True):
    """Compatibility wrapper: missing years represented in wikipedia.links."""
    links = get_missing_links([iata], source, match_by, include_staged)
    return sorted({pd.Timestamp(date).year for date in links['date']})


def _as_data(links):
    data = {}
    for row in links.itertuples(index=False):
        data.setdefault(row.iata, []).append({'date': row.date, 'link': row.link})
    return data


def update_links(data):
    """Explicitly register links without replacing/deleting existing entries.

    This is not called by restoration. Existing registry rows are preserved.
    """
    query = text("""
        INSERT INTO wikipedia.links (iata, date, link)
        SELECT :iata, CAST(:date AS date), :link
        WHERE NOT EXISTS (
            SELECT 1 FROM wikipedia.links
            WHERE iata = :iata AND date::date = CAST(:date AS date) AND link = :link
        )
    """)

    for iata, items in data.items():
        for item in items:
            execute_sql_and_commit(query, {'iata': iata, 'date': pd.Timestamp(item['date']).date(), 'link': item['link']})


def _empty_result_status(browser, link):
    """A parsing failure or an error page is not evidence for deletion."""
    source = browser.page_source or ''
    if 'mw-parser-output' not in source:
        return 'errors', 'Не подтверждена загрузка статьи Wikipedia'
    
    title = re.search(r'<title\b[^>]*>(.*?)</title>', source, re.I | re.S)
    expected = parse_qs(urlparse(link).query).get('title', [''])[0].replace('_', ' ')
    actual = unescape(re.sub(r'<[^>]+>', '', title.group(1))) if title else ''
    normalize = lambda value: re.sub(r'\s+', ' ', value).strip().casefold()

    if not expected or normalize(expected) not in normalize(actual):
        return 'errors', 'Загружена другая страница или не удалось проверить заголовок'
    
    headings = re.findall(r'<h[1-6]\b[^>]*>(.*?)</h[1-6]\s*>', source, re.I | re.S)

    for heading in headings:
        heading = unescape(re.sub(r'<[^>]+>', ' ', heading))
        if (re.search(r'destinations?|airlines?|passenger', heading, re.I)
                and not re.search(r'former|cargo|freight|lounges?', heading, re.I)):
            return 'needs_review', 'Раздел направлений есть, но парсер вернул 0 строк'
        
    cells = re.findall(r'<th\b[^>]*>(.*?)</th>', source, re.I | re.S)
    labels = [normalize(unescape(re.sub(r'<[^>]+>', ' ', cell))) for cell in cells]

    if any(re.search(r'\bairlines?\b', cell) for cell in labels):
        return 'needs_review', 'Есть таблица авиакомпаний; требуется проверка парсера'
    
    return 'delete_candidates', 'Не найден раздел или заголовки таблицы направлений'


def _save_restored(iata, restored):
    """Keep the existing Excel workflow; DB import remains a separate step."""
    existing = _read_saved(iata)
    frame = pd.concat([existing, restored], ignore_index=True)
    frame['date'] = pd.to_datetime(frame['date'], errors='raise').dt.normalize()
    frame = frame.drop_duplicates(subset=COLUMNS).reset_index(drop=True)
    new_path, old_path = _saved_paths(iata)[:2]
    path = new_path if new_path.exists() or not old_path.exists() else old_path
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.xlsx')
    os.close(descriptor)

    try:
        frame.to_excel(temporary, index=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

    return str(path)


def parse_selected_links(data, manual_accept=False, register_links=False):
    """Parse supplied snapshots, save accepted results and report empty pages.

    Returns restored/delete_candidates/needs_review/errors/rejected lists.
    Candidates are printed only; no DELETE is executed.
    """
    global driver
    report = {key: [] for key in (
        'restored', 'delete_candidates', 'needs_review', 'errors', 'rejected')}
    owns_driver = False
    seen = set()
    try:
        if register_links:
            update_links(data)
        for iata, items in data.items():
            for item in items:
                entry = {'iata': iata, 'date': item['date'], 'link': item['link']}
                try:
                    entry['date'] = pd.Timestamp(entry['date']).date()
                    key = (iata, entry['date'], entry['link'])
                    if key in seen:
                        continue

                    seen.add(key)
                    if driver is None:
                        driver = get_driver()
                        owns_driver = True
                    page = WikiAirportPage(entry['link'], driver)
                    page.reflect()
                    frame = page.get_flights()
                    
                    if frame.empty:
                        status, reason = _empty_result_status(driver, entry['link'])
                        entry['reason'] = reason
                        report[status].append(entry)
                        label = ('КАНДИДАТ НА УДАЛЕНИЕ' if status == 'delete_candidates' else 'ПРОВЕРИТЬ ПАРСЕР' if status == 'needs_review' else 'ОШИБКА')
                        print(f"{label}: {iata} | {entry['date']} | {entry['link']} | {reason}")
                        continue

                    frame = frame.copy()
                    frame['date'] = entry['date']
                    frame['origin'] = iata
                    if manual_accept:
                        print(frame.to_string(index=False))
                        if input(f"Сохранить {iata} за {entry['date']}? [y/N] ").strip().lower() != 'y':
                            report['rejected'].append(entry)
                            continue

                    entry['file'] = _save_restored(iata, frame)
                    entry['rows'] = len(frame)
                    report['restored'].append(entry)
                    print(f"ВОССТАНОВЛЕНО: {iata} | {entry['date']} | {len(frame)} строк")
                
                except Exception as exc:
                    # Continue with other links; never mark exceptions for deletion.
                    entry['reason'] = f'{type(exc).__name__}: {exc}'
                    report['errors'].append(entry)
                    print(f"ОШИБКА: {iata} | {entry['date']} | {entry['link']} | {entry['reason']}")
    
    finally:
        if owns_driver and driver is not None:
            driver.quit()
            driver = None
    
    return report


def parse_selected_years(data, manual_accept=False):
    """Parse only the years already represented in the registry."""
    selected = {}
    for iata, years in data.items():
        selected.update(_as_data(_query_links([iata], years)))
    return parse_selected_links(selected, manual_accept=manual_accept)


def restore_missing_data(airports, match_only=False, manual_accept=True, source='db', match_by='date', include_staged=True):
    """Restore missing registry snapshots; match_only does not open Selenium.

    Excel output is saved under Config.FOLDER/parsers/wikipedia/in progress.
    Data and links are not automatically inserted/deleted in the database.
    """
    links = get_missing_links(airports, source, match_by, include_staged)
    data = _as_data(links)
    raw_files = [f.replace(".xlsx", "") for f in os.listdir('d:/Sasha/Самолёты/Flightradar24 project/parsers/wikipedia/raw files')]
    for iata, items in data.items():
        if iata not in raw_files:
            print(f"{iata}: {len(items)} ссылок без данных")
            for item in items:
                print(f"  {item['date']} | {item['link']}")

    if match_only:
        return data
    
    return parse_selected_links(data, manual_accept=manual_accept)

