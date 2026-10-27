"""G8: cross-check against the English attachment, an independent rendering of the same announcement.

Per event, per table row (aligned by position), per day (today / tomorrow): does the English text say
something was "Cancelled"? Compare with whether our records for that row's city and forDate stop work/school.
"""
import collections
import json
import re

import audit

parse = audit.parse
META = json.loads((parse.CACHE / 'meta.json').read_text())
DAY = re.compile(r'Tomorrow|Today|Next (?:Morning|Afternoon|Evening)|This (?:Morning|Afternoon|Evening)|on \d{1,2}-\w{3}-\d{4}', re.I)
SENTENCE_END = re.compile(r'\.(?:\s|$)')  # 'p.m.. Work' ends at the second dot
# English wording of 'suspended': explicit Cancelled, or 'Criteria Met for Cancellation' (= 已達標準, not 'Not Met')
SUSPEND = re.compile(r'Cancelled|(?<!Not )Met for Cancellation', re.I)


# Differences that were investigated and are a property of the SOURCE, not of our parsing.
# pid 7460 (2017-06-02): the English attachment contains 'Tomorrow' sentences that the Chinese attachment
# lacks entirely (updated 2 minutes apart). The next day's own announcement (pid for 2017-06-03) confirms
# the English side was right, and that day's data is complete.
EXPLAINED = {('7460', '苗栗縣'), ('7460', '嘉義縣'), ('7460', '高雄市')}


def eng_attachment(pid):
    for i, (_, t) in enumerate(META[pid]):
        if parse.NOT_CHINESE_ATT.search(t):
            return parse.CACHE / f'{pid}.att{i}'
    return None


def table_rows(path):
    s = parse.decode(path.read_bytes())
    out = []
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.S | re.I):
        c = [parse.clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
        out.append(c)
    return out


def zh_rows(pid):
    att = parse.pick_attachment(pid, META[pid])
    rows = []
    for c in table_rows(att):
        if len(c) in (2, 3) and parse.CITY_RE.match(c[-2]) and '名稱' not in c[-2]:
            rows.append(parse.norm_city(c[-2]))
    return rows


def en_rows(pid):
    """Rows of the English table: 2/3-cell rows whose status cell is non-empty and not a header."""
    rows = []
    for c in table_rows(eng_attachment(pid)):
        if len(c) in (2, 3) and c[-1] and not re.search(r'County/City|Status|Government|名稱', c[-1] + c[-2]):
            rows.append(c)
    return rows


def en_cancelled_days(text):
    """-> set of 'today'/'tomorrow' for which the English text reports something Cancelled."""
    days = set()
    for m in SUSPEND.finditer(text):
        end = SENTENCE_END.search(text, m.end())
        d = DAY.search(text, m.end(), end.start() if end else len(text))  # same sentence only
        if d and d.group().lower() in ('tomorrow', 'next morning', 'next afternoon', 'next evening'):
            days.add('tomorrow')
        else:
            days.add('today')
    return days


def english():
    mism, unaligned, verified, rows_checked, none_eng, skipped_unparsed, explained = [], [], 0, 0, 0, 0, 0
    for ev in audit.load_events():
        if not ev['parsed']:
            continue
        pid = ev['sourceUrl'].split('pid=')[1]
        if eng_attachment(pid) is None:
            none_eng += 1
            continue
        cities = zh_rows(pid)
        en = en_rows(pid)
        if len(cities) != len(en):
            unaligned.append(f'{ev["date"]} pid={pid}: zh rows {len(cities)} != en rows {len(en)}')
            continue
        verified += 1
        by_city = collections.defaultdict(lambda: {'today': False, 'tomorrow': False})
        # ours, aggregated per city (a city may appear in only one row per event: G5)
        for a in ev['areas']:
            if a['work'] == 'stop' or a['school'] in ('stop', 'partial'):
                by_city[a['city']]['today' if a['forDate'] == ev['date'] else 'tomorrow'] = True
        unparsed_cities = {a['city'] for a in ev['areas'] if a['work'] is None}
        for city, c in zip(cities, en):
            if city in unparsed_cities:
                skipped_unparsed += 1
                continue
            rows_checked += 1
            theirs = en_cancelled_days(c[-1])
            ours = {k for k, v in by_city[city].items() if v}
            if theirs != ours and (pid, city) in EXPLAINED:
                explained += 1
            elif theirs != ours:
                mism.append(f'{ev["date"]} pid={pid} {city}: zh-derived {sorted(ours)} vs en {sorted(theirs)} | {c[-1][:90]}')
    print(f'events with english attachment: aligned={verified} unaligned={len(unaligned)}; '
          f'events without english={none_eng}; rows compared={rows_checked}; rows skipped (contain unparsed sentence)={skipped_unparsed}; explained source discrepancies={explained}; unexplained mismatches={len(mism)}')
    for x in unaligned[:30]:
        print('  UNALIGNED', x)
    for x in mism[:60]:
        print('  MISMATCH', x)
    (parse.CACHE / 'english_audit.txt').write_text('\n'.join(['UNALIGNED'] + unaligned + ['MISMATCH'] + mism) + '\n')
    ok = not mism and not unaligned
    print('G8 PASS' if ok else 'G8 FAIL')
    return 0 if ok else 1
