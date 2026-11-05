"""Find short hinterland-size dips and extend a JSON queue for manual reparsing.

Run in the project environment: python low_years.py
Or import evaluate_data_completeness / find_incomplete_years.
Database configuration is loaded only when needed; Selenium is not imported.
"""

import json
import math
import os
import tempfile
import typing as ty
from pathlib import Path
from sqlalchemy import text

from src.sql_utils import read_sql
from src.config import CONFIG


def get_hinterland_sizes(cities: ty.Union[tuple, None] = None):
    """Count unique destination cities by origin airport and calendar year.

    Uses the raw route table and wiki_name/city mapping, avoiding airport and
    airline duplicates. Unmatched destinations are not counted as cities.
    For a different DB view/seasonal slice pass your own data to
    evaluate_data_completeness(iata/year/size columns).
    """

    query = """SELECT * FROM wikipedia.hinterland_size_dynamics"""
    if cities is not None:
        query += """ WHERE city IN %s""" %str(cities)

    return read_sql(text(query))


def find_incomplete_years(data, drop_fraction=0.5, max_run=2,
                          neighbor_rule='both', include_edges=True,
                          min_reference=1):
    """Find short low blocks in a DataFrame with iata/year/size columns.

    both: reference=min(left, right); either: reference=max(left, right).
    At an enabled series edge use the single available neighbor. All block
    values must be <= reference * (1-drop_fraction). A qualifying block must
    be maximal at that threshold: adjacent low years may not be truncated to
    max_run. Calendar gaps are not treated as series edges or bridged.
    Returned years are suspected incompleteness, not confirmed missing data.
    """

    frame = data[['city', 'year', 'hinterland_size']].copy()
    
    found = {}
    for iata, group in frame.groupby('city'):
        group = group.sort_values('year')
        years = group['year'].tolist()
        sizes = group['hinterland_size'].tolist()
        suspicious = set()
        n = len(years)
        for length in range(1, max_run + 1):
            for start in range(n - length + 1):
                stop = start + length  # exclusive
                if any(years[j] != years[j - 1] + 1 for j in range(start + 1, stop)):
                    continue
                # A gap inside the series is not a one-sided edge observation.
                if start > 0 and years[start] != years[start - 1] + 1:
                    continue
                if stop < n and years[stop] != years[stop - 1] + 1:
                    continue
                left = sizes[start - 1] if start > 0 else None
                right = sizes[stop] if stop < n else None
                neighbors = [v for v in (left, right) if v is not None]
                if not neighbors or (len(neighbors) == 1 and not include_edges):
                    continue
                reference = (min(neighbors) if neighbor_rule == 'both' else max(neighbors))
                if reference < min_reference:
                    continue
                cutoff = reference * (1 - drop_fraction)
                is_low = lambda value: (value <= cutoff or math.isclose(
                    value, cutoff, rel_tol=1e-12, abs_tol=1e-12))
                if not all(is_low(value) for value in sizes[start:stop]):
                    continue
                # Avoid flagging part of a 3+ year decline as a short dip.
                if any(is_low(value) for value in neighbors):
                    continue
                suspicious.update(years[start:stop])

        if suspicious:
            found[iata] = sorted(suspicious)

    return found


def merge_incomplete_years_json(new_data, output_path):
    """Union with existing JSON, preserving previous airports and years.

    Invalid existing JSON raises an error and is left untouched. Replacement
    of the physical file is atomic; its existing logical contents are merged.
    Intended for sequential script runs, not concurrent writers.
    """
    path = Path(output_path)
    if path.exists():
        with path.open('r', encoding='utf-8') as stream:
            existing = json.load(stream)
    else:
        existing = {}

    merged = {}
    for mapping in (existing, new_data):
        if not isinstance(mapping, dict):
            raise ValueError('Expected JSON object: {"City": [year, ...]}')
        for code, years in mapping.items():
            merged.setdefault(code.strip(), set()).update([int(y) for y in years])

    result = {code: sorted(years) for code, years in sorted(merged.items())}
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix='.json')
    os.close(descriptor)

    try:
        with open(temporary, 'w', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=4)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)

    return result


def evaluate_data_completeness(city: ty.Union[str, tuple] = '*', output_path="incomplete_years.json",
                               drop_fraction=0.5, max_run=3,
                               neighbor_rule='either', include_edges=True,
                               min_reference=1):
    """Find short dips, extend the JSON queue and return this run's findings.

    No Selenium calls, reparsing or database writes are performed. Previously
    recorded years stay in the queue even if corrected later; remove them
    manually when the investigation is complete.
    """
    if city == '*':
        city = None

    data = get_hinterland_sizes(city)
    found = find_incomplete_years(data, drop_fraction, max_run, neighbor_rule, include_edges, min_reference)
    if output_path is None:
        output_path = Path(CONFIG.FOLDER) / 'parsers' / 'wikipedia' / 'incomplete_years.json'

    merged = merge_incomplete_years_json(found, output_path)
    print(f'Найдено в этом запуске: {sum(map(len, found.values()))} лет; '
          f'в JSON всего: {sum(map(len, merged.values()))}. Файл: {output_path}')
    
    return found
