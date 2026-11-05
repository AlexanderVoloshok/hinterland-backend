import re
from selenium.webdriver.common.by import By
from parsers.wikipedia.wiki_utils import _WikiHTML, _WikiNode

#MAN
def manchester(driver):
    airlines, destinations = [], []
    elements = [el.text for el in driver.find_elements(By.XPATH, '//table[@class="collapsible wikitable collapsed mw-collapsible mw-made-collapsible"]/tbody/tr/td')]
    for x,el in enumerate(elements):
        if x%2 == 0:
            airlines.append(el)
        else:
            destinations.append(el)
    return airlines, destinations

def caracas(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            f'//table[@class="wikitable sortable mw-collapsible jquery-tablesorter mw-made-collapsible"][1]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations


#На случай, если таблиц несколько и они раскрывающиеся, например, для Внуково
def vnukovo(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            f'//table[@class="collapsible wikitable collapsed mw-collapsible mw-made-collapsible"]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations


def domodedovo(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            f'//table[@class="wikitable collapsed"]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations


def fra(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            '//table[@class="wikitable sortable jquery-tablesorter"]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations

def vno(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            '//table[@class="wikitable sortable jquery-tablesorter"][1]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations


def tll(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            f'//table[@class="wikitable sortable jquery-tablesorter"][2]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations


def mnl(driver):
    airlines, destinations = [], []
    passenger_tables = driver.find_elements(By.XPATH, 
                            f'//table[@class="wikitable sortable jquery-tablesorter"][4]')
    for passenger_table in passenger_tables:
        airlines += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{1}]')]
        destinations += [el.text for el in passenger_table.find_elements(By.XPATH, f'tbody/tr/td[{2}]')]
    return airlines, destinations

def lga(driver):
    airlines, destinations = [], []
    li = driver.find_elements(By.XPATH, '//div[@class="mw-content-ltr mw-parser-output"]/ul/li/ul/li')
    for el in li:
        try:
            destinations.append(el.text.split(" (", 1)[1][:-1])
            airlines.append(el.text.split(" (", 1)[0])
        except IndexError:
            pass
    return airlines, destinations

def mex(driver):
    airlines, destinations = [], []
    li = driver.find_elements(By.XPATH, '//div[@class="mw-content-ltr mw-parser-output"]/ul/li/ul/li')
    for el in li:
        try:
            destinations.append(el.text.split(" (", 1)[1][:-1])
            airlines.append(el.text.split(" (", 1)[0])
        except IndexError:
            pass
    li = driver.find_elements(By.XPATH, '//div[@class="mw-content-ltr mw-parser-output"]/ul/li/ul/li/ul/li')
    for el in li:
        try:
            destinations.append(el.text.split(" (", 1)[1][:-1])
            airlines.append(el.text.split(" (", 1)[0])
        except IndexError:
            pass
    return airlines, destinations

def tyo(driver):
    airlines, destinations = [], []
    rows = driver.find_elements(By.XPATH, '//div/ul/li')
    for row in rows:
        elements = row.text.replace("(Scheduled)", "").replace("(Charter)", "").split("\n")
        for el in elements:
            try:
                destinations.append(el.split(" (", 1)[1][:-1])
                airlines.append(el.split(" (", 1)[0])
            except IndexError:
                pass
    return airlines, destinations


def atl(driver):
    airlines, destinations = [], []
    rows = driver.find_elements(By.XPATH, '//ul/li')
    for row in rows:
        elements = row.text.split("\n")
        for el in elements:
            try:
                destinations.append(el.split(" (", 1)[1][:-1])
                airlines.append(el.split(" (", 1)[0])
            except IndexError:
                pass
    rows = driver.find_elements(By.XPATH, '//ul/b/b/li')
    for row in rows:
        elements = row.text.split("\n")
        for el in elements:
            try:
                destinations.append(el.split(" (", 1)[1][:-1])
                airlines.append(el.split(" (", 1)[0])
            except IndexError:
                pass
    return airlines, destinations


def dhl(driver):
    airlines, destinations = [], []
    uls = driver.find_elements(By.XPATH, '//ul/li') + driver.find_elements(By.XPATH, '//ol/li')
    uls = [r.text for r in uls if r.text != '']
    rows = []
    for ul in uls:
        rows.extend([el for el in ul.split("\n") if "(" in el])
    for el in rows:
        try:
            destinations.append(el.split(" (", 1)[1][:-1])
            airlines.append(el.split(" (", 1)[0])
        except IndexError:
            pass
    return airlines, destinations

# Legacy Pittsburgh concourse lists (2007) and tables with nested operators (2009).
_LEGACY_CONCOURSE_HEADINGS = {
    'terminals airlines and destinations',
    'airlines destinations and gate assignments',
}


def has_legacy_concourse_layout(source):
    import re
    from html import unescape

    for title in re.findall(r'<h[2-6]\b[^>]*>(.*?)</h[2-6]\s*>', source, re.I | re.S):
        title = unescape(re.sub(r'<[^>]+>', '', title))
        title = re.sub(r'[^a-z]+', ' ', title.lower()).strip()
        if title in _LEGACY_CONCOURSE_HEADINGS:
            return True
    return False


def pittsburgh_legacy(driver):
    """Return (airlines, destinations) for the two legacy concourse layouts.

    Uses the same HTML tree as the main parser. The local import avoids a
    circular import while utils imports the custom handlers at module load.
    """

    if not has_legacy_concourse_layout(driver.page_source):
        return [], []

    def own_text(node):
        # Nested lists describe other operators; parse their li separately.
        if isinstance(node, str):
            return node
        if node.tag in ('ul', 'ol', 'sup', 'script', 'style'):
            return ''
        classes = set(node.attrs.get('class', '').split())
        if classes.intersection({'reference', 'mw-editsection', 'sortkey'}):
            return ''
        if node.tag == 'a' and 'external' in classes:
            return ''
        if node.tag == 'br':
            return '\n'
        return ''.join(own_text(child) for child in node.children)

    def airline_name(text):
        # Gate metadata can contain commas and must not enter the result.
        text = re.split(r'\bGates?\b', text, maxsplit=1, flags=re.I)[0]
        text = re.sub(r'\s*\(International\)', '', text, flags=re.I)
        return re.sub(r'\s+', ' ', text).strip(' \t\n-–—')

    def destination_notes(text):
        # Keep operational square-bracket notes before remove_link removes
        # references. This also protects commas inside dates.
        def replace(match):
            note = match.group(1)
            if re.search(r'\b(seasonal|charter|hajj|begins?|starts?|ends?|resumes?|suspended|from)\b', note, re.I):
                return '(' + note + ')'
            return ''
        return re.sub(r'\[([^\]]*)\]', replace, text).strip()

    airlines, destinations = [], []

    def add(airline, routes):
        airline = airline_name(airline)
        routes = destination_notes(routes)
        if airline and routes:
            airlines.append(airline)
            destinations.append(routes)

    root = _WikiHTML(driver.page_source).root
    headings = {}
    for node in root.walk():
        if re.fullmatch(r'h[1-6]', node.tag):
            level = int(node.tag[1])
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = re.sub(r'[^a-z]+', ' ', node.text().lower()).strip()
            continue
        if not any(title in _LEGACY_CONCOURSE_HEADINGS for title in headings.values()):
            continue
        section = ' / '.join(headings.values())
        if re.search(r'\b(cargo|freight)\b|\bformer\s+destinations?\b', section, re.I):
            continue

        if node.tag == 'tr':
            cells = [c for c in node.children if isinstance(c, _WikiNode) and c.tag in ('td', 'th')]
            if len(cells) < 2 or cells[0].tag == 'th':
                continue
            # Direct destinations belong to the airline in column 1.
            # Lists in column 2 are processed independently below.
            add(own_text(cells[0]), own_text(cells[1]))
        elif node.tag == 'li':
            text = re.sub(r'\s+', ' ', own_text(node)).strip()
            text = re.sub(r'\s*\(International\)', '', text, flags=re.I)
            prefix, separator, routes = text.partition('(')
            if not separator:
                continue  # A parent airline with only gate info has no routes.
            if routes.endswith(')'):
                routes = routes[:-1]  # Remove only the outer list parenthesis.
            add(prefix, routes)

    return airlines, destinations
