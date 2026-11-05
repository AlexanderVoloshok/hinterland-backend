import re
import time
import warnings
import pandas as pd
import requests
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from parsers.restore_data.links import update_links
from src.config import CONFIG


AIRPORT_PAGE = re.compile(
    r"^(?P<iata>[A-Z]{3})\d[^/]*(?:intro|p\d+)\.html$",
    re.IGNORECASE,
)

DATE_PATTERN = (
    r"\b(?:January|February|March|April|May|June|July|August|"
    r"September|October|November|December)\s+\d{1,2},\s+\d{4}\b"
)

OPTIONS = {
    'INCLUDE': ('ADD', 'AMS','BCN', 'BGO','BRU', 'HEL','LIN', 'MXP', 'ORY', 'CDG'), #,
    'EXCLUDE': ("ZAG", "TIA", "SKP", "BEG", "SJJ", "LJU", "WAW", "KBP", "BTS", "BUD", "BUH", "OTP", "KRK", "RIX", "SOF")
}


def create_session():
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retries))
    session.mount("http://", HTTPAdapter(max_retries=retries))
    return session


def get_airport_links(index_url, session):
    
    def normalize_codes(values):
        if isinstance(values, str):
            values = (values,)
        return {code.strip().upper() for code in values}

    included = normalize_codes(OPTIONS['INCLUDE'])
    excluded = normalize_codes(OPTIONS['EXCLUDE'])

    select_all = "*" in included

    response = session.get(index_url, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")

    date_match = re.search(
        DATE_PATTERN,
        soup.get_text(" ", strip=True),
        re.IGNORECASE,
    )
    if not date_match:
        raise ValueError(f"Не найдена дата выпуска: {index_url}")

    edition_date = pd.to_datetime(
        date_match.group(),
        format="%B %d, %Y",
    )

    heading = soup.find(
        string=re.compile(r"Select\s+Arrival\s+City\s+Below:", re.I)
    )
    if heading is None:
        raise ValueError(f"Не найден список аэропортов: {index_url}")

    links = {}
    found_airport_links = False

    for anchor in heading.find_all_next("a", href=True):
        absolute_url = urljoin(response.url, anchor["href"])
        parts = urlparse(absolute_url)

        if parts.hostname not in {
            "departedflights.com",
            "www.departedflights.com",
        }:
            continue

        filename = parts.path.rsplit("/", 1)[-1]
        match = AIRPORT_PAGE.fullmatch(filename)
        if not match:
            continue

        found_airport_links = True
        iata = match.group("iata").upper()

        if select_all:
            if iata in excluded:
                continue
        elif iata not in included:
            continue

        absolute_url = urlunparse((
            "https",
            "www.departedflights.com",
            parts.path,
            "",
            parts.query,
            "",
        ))

        links.setdefault(absolute_url, {
            "link": absolute_url,
            "date": edition_date,
            "iata": iata,
        })

    # Пустой результат после фильтрации допустим.
    if not found_airport_links:
        raise ValueError(f"Ссылки на аэропорты не найдены: {index_url}")

    return list(links.values())


def merge_csv(path, new_data, columns, sort_by):
    """Объединяет новые данные с предыдущим запуском без точных дублей."""
    if path.exists():
        old_data = pd.read_csv(path, dtype=str, keep_default_na=False)
        if list(old_data.columns) != columns:
            raise ValueError(f"Неожиданные столбцы в {path}")

        data = pd.concat([old_data, new_data], ignore_index=True)
    else:
        data = new_data.copy()

    data["date"] = pd.to_datetime(data["date"], errors="raise")

    data = (
        data[columns]
        .fillna("")
        .drop_duplicates()
        .sort_values(sort_by, kind="stable")
        .reset_index(drop=True)
    )

    # Запись через временный файл защищает существующий CSV
    # от прерывания в процессе сохранения.
    temporary_path = path.with_suffix(".csv.tmp")
    data.to_csv(temporary_path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d")
    temporary_path.replace(path)
    return data


def parse_departedflights_url(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.content, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()

    for br in soup.find_all("br"):
        br.replace_with("\n")

    text = "\n".join(
        re.sub(r"\s+", " ", line).strip()
        for line in soup.get_text(separator=" ").splitlines()
        if line.strip()
    )

    filename = urlparse(url).path.rsplit("/", 1)[-1]
    origin_match = re.match(r"([A-Za-z]{3})(?=\d)", filename)
    if not origin_match:
        raise ValueError(f"Не удалось определить origin: {url}")
    
    origin = origin_match.group(1).upper()

    header = re.search(
        r"Airlines and Aircraft Serving\s+(.+?)\s+Effective\s+"
        r"([A-Za-z]+\s+\d{1,2},\s+\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not header:
        raise ValueError(f"Не найден заголовок с датой: {url}")

    origin_name = header.group(1)
    date = pd.to_datetime(header.group(2), format="%B %d, %Y")

    def normalize(value):
        return re.sub(r"\s+", " ", value).strip().casefold()

    def is_origin(city):
        city = normalize(city)
        name = normalize(origin_name)
        return name == city or name.startswith(city + " ")

    # Допускаем различия регистра и опечатку OperatedL.
    aircraft_label = r"Aircraft\s+Operated\s*[:L]"
    block_pattern = re.compile(
        rf"^([^\n]+)\n{aircraft_label}\s*\n"
        r".*?Destinations?\s+Served:\s*\n"
        r"(.*?)"
        rf"(?=\n[^\n]+\n{aircraft_label}"
        r"|\n(?:<<|MAIN PAGE|DETAILED)\b|\Z)",
        flags=re.MULTILINE | re.DOTALL | re.IGNORECASE,
    )

    note_start = re.compile(r"^(\*+)\s*\(", re.MULTILINE)
    rows = []
    issues = []

    def report(airline, message):
        message = f"{origin} | {airline}: {message}"
        issues.append(message)
        warnings.warn(message, UserWarning, stacklevel=2)

    for airline, body in block_pattern.findall(text):
        airline = airline.strip()

        def make_row(destination, remark=""):
            return {
                "date": date,
                "origin": origin,
                "airline": " ".join([p.capitalize() for p in airline.strip().split(" ")]),
                "destination": destination.replace(" << PREVIOUS PAGE", ""),
                "remark": remark,
            }

        # Разделяем сноски по началу следующей сноски,
        # чтобы сохранить скобки внутри её текста.
        starts = list(note_start.finditer(body))
        remarks = {}

        for i, start in enumerate(starts):
            end = starts[i + 1].start() if i + 1 < len(starts) else len(body)
            note = body[start.end():end].strip()

            if note.endswith(")"):
                note = note[:-1].strip()

            remarks[start.group(1)] = re.sub(r"\s+", " ", note)

        destinations_text = body[:starts[0].start()] if starts else body
        destinations_text = re.sub(r"\s+", " ", destinations_text).strip()

        # Сначала сохраняем все направления из основного списка.
        used_notes = {}

        for item in destinations_text.split(","):
            item = item.strip()
            if not item:
                continue

            marker = re.search(r"\s*(\*+)$", item)
            destination = item[:marker.start()].strip() if marker else item
            rows.append(make_row(destination))

            if marker:
                key = marker.group(1)
                used_notes.setdefault(key, []).append(destination)

        # Общую сноску для нескольких городов разбираем один раз.
        for key, stops in used_notes.items():
            note = remarks.get(key)

            if note is None:
                report(
                    airline,
                    f"Нет сноски {key} для {', '.join(stops)}; направления сохранены без ремарки.",
                )
                continue

            # Конкретные пары городов:
            # between Amsterdam and Kiev ... between Frankfurt and Kiev.
            pairs = re.findall(
                r"\bbetween\s+(.+?)\s+and\s+(.+?)"
                r"(?=\s+and\s+(?:select\s+)?flights\b|[.;]|$)",
                note,
                flags=re.IGNORECASE,
            )

            if pairs:
                # Автоматически обрабатываем только однозначную посадку.
                if len(stops) != 1:
                    report(
                        airline,
                        f"Несколько промежуточных городов; нужна проверка: {note}",
                    )
                    continue

                for first, second in pairs:
                    first, second = first.strip(), second.strip()

                    if is_origin(second):
                        endpoint = first
                    elif is_origin(first):
                        endpoint = second
                    else:
                        report(airline, f"Не определён исходный город: {note}")
                        continue

                    rows.append(make_row(endpoint, f"via {stops[0]}"))

                continue

            # Явная последовательность городов:
            # on Moscow-Simferopol-Cairo-Addis Ababa route.
            chain_match = re.search(r"\bon\s+(.+?)\s+route\b", note, flags=re.IGNORECASE)

            if chain_match:
                chain = [
                    city.strip()
                    for city in re.split(r"\s*[-–—]\s*", chain_match.group(1))
                    if city.strip()
                ]

                if len(chain) < 2:
                    report(airline, f"Не разобрана цепочка: {note}")
                    continue

                # Разворачиваем цепочку в направлении от origin.
                if is_origin(chain[-1]):
                    chain.reverse()
                #elif not is_origin(chain[0]):
                #    report(airline, f"Исходный город не на конце цепочки: {note}",)
                #    continue

                # Первый город после origin уже присутствует
                # в основном списке; остальные добавляем с посадками.
                for i in range(2, len(chain)):
                    rows.append(make_row(chain[i], "via " + ", ".join(chain[1:i])))

                continue

            # Сноска подтверждает посадки, но не называет конечный город.
            # Поэтому дополнительных строк с via создать нельзя.
            if re.search(
                r"\bunpublished en route stops?\s+on select flights\.?$", note, flags=re.IGNORECASE,
            ):
                continue

            report(airline, f"Неизвестный формат сноски; основные направления сохранены: {note}")

    if not rows:
        raise ValueError(f"Блоки авиакомпаний не найдены: {url}")

    df = pd.DataFrame(
        rows, columns=["date", "origin", "airline", "destination", "remark"],
    ).drop_duplicates().reset_index(drop=True)

    # Предупреждения доступны и программно.
    df.attrs["warnings"] = issues
    return df


def parse_editions(index_urls, output_dir, delay=0.5):
    output_dir = Path(output_dir)
    airports_dir = output_dir / "departedflights_airports"
    airports_dir.mkdir(parents=True, exist_ok=True)

    discovered = {}
    errors = []

    with create_session() as session:
        for index_url in dict.fromkeys(index_urls):
            print(f"Раздел: {index_url}")

            try:
                for record in get_airport_links(index_url, session):
                    discovered.setdefault(record["link"], record)
            except Exception as exc:
                errors.append({
                    "link": index_url,
                    "stage": "index",
                    "error": f"{type(exc).__name__}: {exc}",
                })

            time.sleep(delay)

    link_columns = ["link", "date", "iata"]
    links_df = pd.DataFrame(discovered.values(), columns=link_columns)

    # Сохраняем ВСЕ найденные ссылки до начала разбора аэропортов.
    all_links = merge_csv(
        output_dir / "schedule_links.csv",
        links_df,
        columns=link_columns,
        sort_by=["iata", "date", "link"],
    )

    route_columns = [
        "date", "origin", "airline", "destination", "remark"
    ]

    for number, record in enumerate(discovered.values(), start=1):
        url = record["link"]
        print(f"[{number}/{len(discovered)}] {url}")

        try:
            df = parse_departedflights_url(url)

            if df.empty:
                raise ValueError("Парсер вернул пустую таблицу")

            df = df[route_columns].copy()
            df["date"] = pd.to_datetime(df["date"], errors="raise")

            if set(df["origin"]) != {record["iata"]}:
                raise ValueError("origin не совпадает с кодом в ссылке")

            # В реестре сохраняем дату из самого расписания.
            # Для неразобранных страниц останется дата выпуска.
            dates = df["date"].drop_duplicates()
            if len(dates) != 1:
                raise ValueError("На странице обнаружено несколько дат")

            all_links.loc[
                all_links["link"].eq(url), "date"
            ] = dates.iloc[0]

            merge_csv(
                airports_dir / f"{record['iata']}_d.csv",
                df,
                columns=route_columns,
                sort_by=["date", "airline", "destination", "remark"],
            )

        except Exception as exc:
            errors.append({
                "link": url,
                "stage": "airport",
                "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"  Ошибка: {exc}")

        time.sleep(delay)

    all_links.to_excel(output_dir / "schedule_links.xlsx", index=False)

    errors_df = pd.DataFrame(errors, columns=["link", "stage", "error"])
    errors_df.to_excel(output_dir / "errors.xlsx", index=False)

    convert_csv_to_xlsx(output_dir)

    print(f"Готово. Найдено расписаний: {len(discovered)}. Ошибок: {len(errors_df)}.")
    return all_links, errors_df


def convert_csv_to_xlsx(output_dir):
    for csv_path in sorted(Path(output_dir).rglob("*.csv")):
        xlsx_path = csv_path.with_suffix(".xlsx")

        # Строковый тип сохраняет коды, пустые значения и исходный текст.
        df = pd.read_csv(
            csv_path,
            dtype=str,
            keep_default_na=False,
            encoding="utf-8-sig",
        )

        df.to_excel(xlsx_path, index=False, engine="openpyxl")
        csv_path.unlink()


if __name__ == '__main__':
    urls = [
        "https://www.departedflights.com/80intro.html",
        "https://www.departedflights.com/83Iintro.html",
        "https://www.departedflights.com/89Iintro.html",
        "https://www.departedflights.com/96Iintro.html"
    ]

    links_df, errors_df = parse_editions(urls, output_dir=CONFIG.DATA_SAVE_FOLDER)
    update_links(links_df)
