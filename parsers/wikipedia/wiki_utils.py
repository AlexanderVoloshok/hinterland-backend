import re
from html.parser import HTMLParser


def remove_link(name: str):
    """Remove citation markers/URLs without discarding link labels."""
    name = re.sub(r'https?://[^\s<>\]]+', '', name)
    name = re.sub(r'\[[^\]]*\]', '', name)
    name = re.sub(r'[\u200b-\u200f\u202a-\u202e\u2060\ufeff]', '', name)
    return re.sub(r'[^\S\n]+', ' ', name.replace('\xa0', ' ')).strip()


def split_destinations(text):
    """Split outside parentheses; normalize notes attached to airport names.

    For example, Fort Myers(Begins November 3) becomes one token:
    Fort Myers (Begins November 3). Commas inside dates remain in the note.
    """
    text = re.sub(r'(?<=\S)\(', ' (', remove_link(text))
    depth = 0
    start = 0
    for i, char in enumerate(text):
        if char == '(':
            depth += 1
        elif char == ')':
            depth = max(0, depth - 1)
        elif char in ',;\n' and depth == 0:
            if text[start:i].strip():
                yield text[start:i].strip()
            start = i + 1
    if text[start:].strip():
        yield text[start:].strip()


def unify_symbols(name: str):
    return name.replace("-", "–").replace(")", "")


def clearify_airport_name(name: str):
    """Separate an airport name and its note, with or without a space."""
    name = remove_link(name).replace('*', '').strip()
    group = None
    prefix = re.match(r'^(Seasonal charter|Seasonal|Charter|Hajj)\s*:\s*', name, re.I)
    if prefix:
        group = prefix.group(1).title()
        name = name[prefix.end():].strip()

    parts = re.split(r'\s*\(', name, maxsplit=1)
    destination = parts[0].strip()
    if len(parts) == 1:
        return destination, group

    # Keep the entire note (including commas in dates) for filtering later.
    remark = parts[1].strip()
    if remark.endswith(')'):
        remark = remark[:-1].strip()
    return destination, remark or group


def _read_wiki_tables(source):
    """Read all passenger tables in document order, including collapsed cells."""
    root = _WikiHTML(source).root
    heading = ''
    headings = {}
    for node in root.walk():
        if node.tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            level = int(node.tag[1])
            headings = {k: v for k, v in headings.items() if k < level}
            headings[level] = remove_link(node.text())
            heading = ' / '.join(headings.values())
        elif node.tag == 'table':
            node.section_heading = heading
    result = []
    for table in root.walk('table'):
        if 'wikitable' not in table.attrs.get('class', '').split():
            continue
        section = table.section_heading
        if re.search(r'\b(cargo|freight)\b|\bformer\s+destinations?\b', section, re.I):
            continue
        def belongs(node):
            parent = node.parent
            while parent is not None and parent.tag != 'table':
                parent = parent.parent
            return parent is table
        rows = [r for r in table.walk('tr') if belongs(r)]
        ai = di = None
        spans = {}
        for row in rows:
            cells = [c for c in row.children if isinstance(c, _WikiNode) and c.tag in ('td', 'th')]
            labels = [re.sub(r'\s+', ' ', remove_link(c.text())).strip().lower() for c in cells]
            if any(x in ('airline', 'airlines') for x in labels) and any(x in ('destination', 'destinations') for x in labels):
                ai = next(i for i, x in enumerate(labels) if x in ('airline', 'airlines'))
                di = next(i for i, x in enumerate(labels) if x in ('destination', 'destinations'))
                spans = {}
                continue
            if ai is None:
                continue
            columns = {}
            for i, (value, left) in list(spans.items()):
                columns[i] = value
                if left > 1:
                    spans[i] = (value, left - 1)
                else:
                    del spans[i]
            i = 0
            for cell in cells:
                while i in columns:
                    i += 1
                value = remove_link(cell.text())
                colspan = max(1, int(cell.attrs.get('colspan', '1')))
                rowspan = max(1, int(cell.attrs.get('rowspan', '1')))
                for _ in range(colspan):
                    columns[i] = value
                    if rowspan > 1:
                        spans[i] = (value, rowspan - 1)
                    i += 1
            if columns.get(ai) and columns.get(di):
                result.append(dict(airline=columns[ai], destinations=columns[di],
                                   charter=bool(re.search(r'\bcharter', section, re.I))))
    return result


class _WikiNode:
    def __init__(self, tag='', attrs=(), parent=None):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []

    def walk(self, tag=None):
        for child in self.children:
            if isinstance(child, _WikiNode):
                if tag is None or child.tag == tag:
                    yield child
                yield from child.walk(tag)

    def text(self):
        classes = set(self.attrs.get('class', '').split())
        if self.tag in ('sup', 'script', 'style') or classes.intersection({
            'reference', 'mw-editsection', 'sortkey', 'mw-cite-backlink',
            'sortbutton', 'mw-collapsible-toggle'
        }):
            return ''
        if self.tag == 'a' and 'external' in classes:
            return ''
        if self.tag == 'br':
            return '\n'
        value = ''.join(c.text() if isinstance(c, _WikiNode) else c for c in self.children)
        return value + ('\n' if self.tag in ('p', 'div', 'li') else '')


class _WikiHTML(HTMLParser):
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input',
            'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = _WikiNode()
        self.current = self.root
        self.feed(source)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = _WikiNode(tag, attrs, self.current)
        self.current.children.append(node)
        if tag not in self.VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        node = self.current
        while node.parent is not None:
            if node.tag == tag:
                self.current = node.parent
                return
            node = node.parent

    def handle_data(self, data):
        self.current.children.append(data)