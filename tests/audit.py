"""Independent audit of data/ against the raw cache. Used by test_data.py and runnable directly.

Checks (each returns a list of problem strings):
  raw_in_source   every area.raw occurs in its source cell
  no_loss         source cell text is fully accounted for by area.raw + dropped noise
  canonical       simple whole-sentence statuses map to the expected work/school/period
  dates           forDate / publishedAt / updatedAt are plausible against the event date
"""
import datetime
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import parse  # noqa: E402

STRIP = lambda s: re.sub(r'\s+', '', s)  # noqa: E731

# Whole sentences with no scope/time -> (work, school). Written by hand, independent of parse.py.
CANONICAL = {
    '今天停止上班、停止上課。': ('stop', 'stop'),
    '今天停止辦公、停止上課。': ('stop', 'stop'),
    '今天照常上班、照常上課。': ('normal', 'normal'),
    '今天照常辦公、照常上課。': ('normal', 'normal'),
    '今天照常上班、停止上課。': ('normal', 'stop'),
    '今天照常辦公、停止上課。': ('normal', 'stop'),
    '今天已達停止上班及上課標準。': ('stop', 'stop'),
    '今天已達停止辦公及上課標準。': ('stop', 'stop'),
    '今天未達停止上班及上課標準。': ('normal', 'normal'),
    '今天未達停止辦公及上課標準。': ('normal', 'normal'),
    '今天未達停止上班、已達停止上課標準。': ('normal', 'stop'),
    '明天停止上班、停止上課。': ('stop', 'stop'),
    '明天照常上班、照常上課。': ('normal', 'normal'),
    '明天已達停止上班及上課標準。': ('stop', 'stop'),
    '明天未達停止上班及上課標準。': ('normal', 'normal'),
}


def load_events():
    out = []
    for f in sorted((ROOT / 'data').glob('*.json')):
        out += json.loads(f.read_text(encoding='utf-8'))
    return out


def source_cells(pid_to_meta, ev):
    """city -> concatenated cell text (whitespace removed), straight from the cached attachment."""
    pid = ev['sourceUrl'].split('pid=')[1]
    att = parse.pick_attachment(pid, pid_to_meta[pid])
    if att is None:
        return None
    s = parse.decode(att.read_bytes())
    cells = {}
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.S | re.I):
        c = [parse.clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
        if len(c) in (2, 3) and parse.CITY_RE.match(c[-2]) and '名稱' not in c[-2]:
            city = parse.norm_city(c[-2])
            cells[city] = cells.get(city, '') + STRIP(c[-1])
    return cells


def run_all():
    meta = json.loads((parse.CACHE / 'meta.json').read_text())
    problems = {'raw_in_source': [], 'no_loss': [], 'canonical': [], 'dates': []}
    d = lambda s: datetime.datetime.strptime(s, '%Y%m%d').date()  # noqa: E731
    for ev in load_events():
        tag = f"{ev['date']} pid={ev['sourceUrl'].split('pid=')[1]}"
        # dates
        pub = d(ev['publishedAt'])
        if pub < d(ev['date']) or (pub - d(ev['date'])).days > 400:
            problems['dates'].append(f'{tag} publishedAt {ev["publishedAt"]}')
        if ev['updatedAt']:
            up = datetime.date.fromisoformat(ev['updatedAt'][:10])
            if not -1 <= (up - d(ev['date'])).days <= 1:
                problems['dates'].append(f'{tag} updatedAt {ev["updatedAt"]}')
        for a in ev['areas']:
            if (d(a['forDate']) - d(ev['date'])).days not in (0, 1):
                problems['dates'].append(f'{tag} forDate {a["forDate"]}')
        cells = source_cells(meta, ev)
        if cells is None:
            continue  # inline events: raw only, covered by parsed=false
        by_city = {}
        for a in ev['areas']:
            by_city.setdefault(a['city'], []).append(a)
            if STRIP(a['raw']) not in cells.get(a['city'], ''):
                problems['raw_in_source'].append(f'{tag} {a["city"]}: {a["raw"][:40]}')
            if a['raw'] in CANONICAL and (a['work'], a['school']) != CANONICAL[a['raw']]:
                problems['canonical'].append(f'{tag} {a["city"]}: {a["raw"]} -> {a["work"]}/{a["school"]}')
        for city, text in cells.items():
            rest = text
            seen = set()
            for a in by_city.get(city, []):
                if a['raw'] not in seen:
                    seen.add(a['raw'])
                    rest = rest.replace(STRIP(a['raw']), '', 1)
            rest = re.sub(r'尚未列入警戒區。?|尚未宣布消息。?', '', rest)
            if rest:
                problems['no_loss'].append(f'{tag} {city}: leftover {rest[:50]}')
    return problems


if __name__ == '__main__':
    for name, items in run_all().items():
        print(f'## {name}: {len(items)}')
        for x in items[:25]:
            print('  ', x)
