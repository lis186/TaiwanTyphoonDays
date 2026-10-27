"""Exhaustive audit of data/ (no sampling). One subcommand per gate; each prints 'G<n> PASS|DONE ...'.

Usage: python3 tests/audit_full.py <coverage|cache-integrity|header-date|city-rows|times|english|forecast|hygiene|readme>
Most gates read .cache/ (see scripts/fetch_all.py). Offline: nothing here touches the network.
"""
import collections
import datetime
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import audit  # noqa: E402

ROOT, parse = audit.ROOT, audit.parse
CACHE = parse.CACHE
EVENTS = audit.load_events()
ITEMS = json.loads((CACHE / 'all_items.json').read_text())
META = json.loads((CACHE / 'meta.json').read_text())
PID = lambda e: e['sourceUrl'].split('pid=')[1]  # noqa: E731


def verdict(name, problems, extra=''):
    if problems:
        print(f'{name} FAIL {len(problems)} problems {extra}')
        for p in problems[:40]:
            print('  ', p)
        return 1
    print(f'{name} PASS {extra}')
    return 0


# ---------------------------------------------------------------- G1
def coverage():
    page1 = (CACHE / 'list_page1.html').read_text(encoding='utf-8')
    m = re.search(r'共\s*<b>(\d+)</b>\s*筆', page1)
    total = int(m.group(1)) if m else -1
    pages = re.search(r'第\s*<b>1/(\d+)</b>\s*頁', page1)
    probs = []
    if not pages or int(pages.group(1)) != -(-total // 10):
        probs.append(f'page count {pages and pages.group(1)} inconsistent with total {total} at 10/page')
    cache_pids = [p for p, _, _ in ITEMS]
    data_pids = [PID(e) for e in EVENTS]
    if len(cache_pids) != total:
        probs.append(f'cache list has {len(cache_pids)} items, site says {total}')
    if len(set(cache_pids)) != len(cache_pids):
        probs.append('duplicate pids in cache list')
    if len(set(data_pids)) != len(data_pids):
        probs.append('duplicate pids in data')
    if set(cache_pids) != set(data_pids):
        probs.append(f'pid mismatch: only-list={sorted(set(cache_pids) - set(data_pids))[:5]} '
                     f'only-data={sorted(set(data_pids) - set(cache_pids))[:5]}')
    pub = {p: pb for p, pb, _ in ITEMS}
    for e in EVENTS:
        want = parse.roc_to_ad(pub[PID(e)].split('.')).strftime('%Y%m%d')
        if e['publishedAt'] != want:
            probs.append(f'{PID(e)} publishedAt {e["publishedAt"]} != list {want}')
    return verdict('G1', probs, f'pids={len(data_pids)} site_total={total}')


# ---------------------------------------------------------------- G2
def cache_integrity():
    """Local only: every referenced file exists, is non-empty, decodes, and looks like a complete HTML document."""
    probs, n_att = [], 0
    for pid, _, _ in ITEMS:
        d = CACHE / f'{pid}.detail'
        if not d.exists() or d.stat().st_size < 5000:
            probs.append(f'{pid}: detail missing/tiny')
        for i, _ in enumerate(META[pid]):
            f = CACHE / f'{pid}.att{i}'
            n_att += 1
            if not f.exists() or f.stat().st_size < 200:
                probs.append(f'{pid}: att{i} missing/tiny')
                continue
            s = parse.decode(f.read_bytes())
            if '\ufffd' in s:
                probs.append(f'{pid}: att{i} has undecodable bytes')
            if not re.search(r'</html>\s*$', s, re.I) and '</table>' not in s.lower():
                probs.append(f'{pid}: att{i} looks truncated')
    extra = {f.name for f in CACHE.iterdir() if re.match(r'\d+\.(detail|att\d+)$', f.name)}
    want = {f'{p}.detail' for p, _, _ in ITEMS} | {f'{p}.att{i}' for p, _, _ in ITEMS for i in range(len(META[p]))}
    if extra != want:
        probs.append(f'cache files differ from manifest: extra={sorted(extra - want)[:3]} missing={sorted(want - extra)[:3]}')
    return verdict('G2', probs, f'details={len(ITEMS)} attachments={n_att}')


# ---------------------------------------------------------------- G3
WD = '一二三四五六日'


def header_date():
    probs, n, wd = [], 0, 0
    for e in EVENTS:
        pid = PID(e)
        att = parse.pick_attachment(pid, META[pid])
        if att is None:
            continue
        s = parse.clean(parse.decode(att.read_bytes()))
        m = re.search(r'(\d+)年\s*(\d+)月\s*(\d+)日\s*(?:[（(]星期(.)[)）])?\s*天然災害', s)
        if not m:
            probs.append(f'{pid}: no header date')
            continue
        n += 1
        d = parse.roc_to_ad(m.groups()[:3])
        if d.strftime('%Y%m%d') != e['date']:
            probs.append(f'{pid}: header {d} != date {e["date"]}')
        if m.group(4):
            wd += 1
            if WD[d.weekday()] != m.group(4):
                probs.append(f'{pid}: weekday {m.group(4)} != computed {WD[d.weekday()]} for {d}')
    return verdict('G3', probs, f'headers_checked={n} weekdays_checked={wd}')


# ---------------------------------------------------------------- G5
EXPLAINED_CITY_SET = {}  # filled after review: pid -> reason


def city_rows():
    per_event, probs = {}, []
    for e in EVENTS:
        pid = PID(e)
        att = parse.pick_attachment(pid, META[pid])
        if att is None:
            continue
        s = parse.decode(att.read_bytes())
        rows = []
        full = False
        for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.S | re.I):
            c = [parse.clean(x) for x in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
            if len(c) in (2, 3) and parse.CITY_RE.match(c[-2]) and '名稱' not in c[-2]:
                rows.append(parse.norm_city(c[-2]))
                full = full or len(c) == 3
        per_event[pid] = (e['date'], rows, full)
        dup = [c for c, k in collections.Counter(rows).items() if k > 1]
        if dup:
            probs.append(f'{pid} {e["date"]}: duplicate city rows {dup}')
    # full-table events (those with a 區域 column): city set must be identical within an administrative era
    sets = collections.defaultdict(list)
    for pid, (d, rows, full) in per_event.items():
        if full:
            sets[frozenset(rows)].append((d, pid))
    print('distinct full-table city sets:', len(sets))
    for s, evs in sorted(sets.items(), key=lambda x: min(x[1])):
        ds = sorted(d for d, _ in evs)
        print(f'  {len(s)} cities, {len(evs)} events, {ds[0]}..{ds[-1]}')
    ev_dates = collections.defaultdict(set)
    for s, evs in sets.items():
        for d, pid in evs:
            ev_dates[s].add(d)
    # eras must not interleave: sort distinct sets by first date, ranges must be disjoint
    ranges = sorted((min(v), max(v), len(k)) for k, v in ev_dates.items())
    for a, b in zip(ranges, ranges[1:]):
        if b[0] <= a[1]:
            probs.append(f'city-set eras overlap: {a} vs {b}')
    # every event, partial or full: city names must exist on that date (2010-12-25 merger, 2014-12-25 Taoyuan)
    for e in EVENTS:
        if not e['parsed']:
            continue
        gone = set()
        if e['date'] >= '20101225':
            gone |= {'臺北縣', '臺中縣', '臺南縣', '高雄縣'}
        else:
            gone |= {'新北市'}
        if e['date'] >= '20141225':
            gone |= {'桃園縣'}
        else:
            gone |= {'桃園市'}
        bad = {a['city'] for a in e['areas']} & gone
        if bad:
            probs.append(f'{PID(e)} {e["date"]}: city names not valid on that date: {sorted(bad)}')
    return verdict('G5', [p for p in probs if p.split(':')[0] not in EXPLAINED_CITY_SET],
                   f'events_with_tables={len(per_event)}')


# ---------------------------------------------------------------- G6
AMPM = {'上午': 0, '中午': 0, '下午': 12, '晚上': 12}


def times():
    probs, n = [], 0
    for e in EVENTS:
        for a in e['areas']:
            if a['period'] != 'from':
                continue
            n += 1
            raw = re.sub(r'\s+', '', a['raw'])
            # independent: find the time token that precedes 起, then recompute from digits
            m = re.search(r'(上午|中午|下午|晚上)(\d{1,2})(?:[:：](\d{2})|時(?:(\d{1,2})分)?)起', raw)
            if not m:
                probs.append(f'{e["date"]} no time token: {raw[:50]}')
                continue
            h = int(m.group(2))
            mi = int(m.group(3) or m.group(4) or 0)
            h24 = h % 12 + AMPM[m.group(1)] if h != 12 else 12 if m.group(1) in ('中午', '下午') else 0
            if m.group(1) == '上午' and h == 12:
                probs.append(f'{e["date"]} 上午12 ambiguous: {raw[:50]}')
            want = f'{h24:02d}:{mi:02d}'
            if want != a['from']:
                probs.append(f'{e["date"]} {raw[:50]}: data {a["from"]} != independent {want}')
    return verdict('G6', probs, f'from_records={n}')


# ---------------------------------------------------------------- G9
def forecast():
    by_for = collections.defaultdict(lambda: {'today': [], 'forecast': []})
    for e in EVENTS:
        for a in e['areas']:
            if a['work'] is None:
                continue
            by_for[a['forDate']]['today' if a['forDate'] == e['date'] else 'forecast'].append((e['date'], a))
    conflicts, agree, only_fc = [], 0, 0

    def stops(recs):  # city -> any full-day-or-later stop for whole city
        out = collections.defaultdict(set)
        for _, a in recs:
            if a['scope'] == '':
                out[a['city']].add('stop' if 'stop' in (a['work'], a['school']) else 'normal')
        return out
    for d, v in sorted(by_for.items()):
        if not v['forecast']:
            continue
        if not v['today']:
            only_fc += 1
            continue
        t, f = stops(v['today']), stops(v['forecast'])
        for city in f:
            if city in t and f[city] != t[city]:
                conflicts.append(f'{d} {city}: forecast {sorted(f[city])} vs actual {sorted(t[city])}')
            elif city in t:
                agree += 1
    out = HERE.parent / '.cache' / 'forecast.txt'
    out.write_text('\n'.join(conflicts) + '\n')
    print(f'G9 DONE dates_with_forecast={sum(1 for v in by_for.values() if v["forecast"])} '
          f'forecast_only={only_fc} city_agree={agree} city_conflicts={len(conflicts)} (listed in {out.name})')
    return 0


# ---------------------------------------------------------------- G10
KNOWN_CITIES = set('基隆市 臺北市 新北市 桃園市 新竹市 新竹縣 苗栗縣 臺中市 彰化縣 南投縣 雲林縣 嘉義市 嘉義縣 臺南市 '
                   '高雄市 屏東縣 宜蘭縣 花蓮縣 臺東縣 澎湖縣 連江縣 金門縣 臺北縣 桃園縣 臺中縣 臺南縣 高雄縣'.split())


def hygiene():
    probs = []
    for f in sorted((ROOT / 'data').glob('*.json')):
        text = f.read_text(encoding='utf-8')
        obj = json.loads(text)
        if json.dumps(obj, ensure_ascii=False, indent=2) + '\n' != text:
            probs.append(f'{f.name}: not canonical json serialisation')
        if '\r' in text:
            probs.append(f'{f.name}: CR characters')
    for e in EVENTS:
        for a in e['areas']:
            blob = json.dumps(a, ensure_ascii=False)
            if '�' in blob or re.search(r'[\x00-\x08\x0b-\x1f\x7f-\x9f]', blob):
                probs.append(f'{e["date"]}: bad characters in {a["raw"][:30]}')
            if re.search(r'[㐀-䶿-]', blob):
                probs.append(f'{e["date"]}: private-use/ext-A characters in {a["raw"][:30]}')
            if e['parsed'] and a['city'] not in KNOWN_CITIES:
                probs.append(f'{e["date"]}: unknown city {a["city"]!r}')
            for k in ('city', 'scope', 'raw'):
                if a[k] != a[k].strip():
                    probs.append(f'{e["date"]}: untrimmed {k} {a[k]!r}')
    return verdict('G10', probs, f'areas={sum(len(e["areas"]) for e in EVENTS)}')


# ---------------------------------------------------------------- G11
def readme():
    text = (ROOT / 'README.md').read_text(encoding='utf-8')
    A = [(e, a) for e in EVENTS for a in e['areas']]
    unparsed = {a['raw'].strip() for e in EVENTS if e['parsed'] for a in e['areas'] if a['work'] is None}
    ev_with_null = sum(1 for e in EVENTS if e['parsed'] and any(a['work'] is None for a in e['areas']))
    inline = sum(1 for e in EVENTS if not e['parsed'])
    unparsed_sent = sum(1 for e in EVENTS if e['parsed'] for a in e['areas'] if a['work'] is None)
    # dropped noise: count phrases in the raw source cells independently of parse.py
    noise = 0
    for e in EVENTS:
        att = parse.pick_attachment(PID(e), META[PID(e)])
        if att is None:
            continue
        cells = audit.source_cells(META, e)
        noise += sum(len(re.findall(r'尚未列入警戒區|尚未宣布消息', t)) for t in cells.values())
    dates = {e['date'] for e in EVENTS}
    no_page = sorted({a['forDate'] for e in EVENTS for a in e['areas']
                      if a['forDate'] != e['date'] and 'stop' in (a['work'], a['school']) and a['forDate'] not in dates})
    d0, d1 = EVENTS[0]['date'], EVENTS[-1]['date']
    fmt = lambda s: f'{s[:4]}-{s[4:6]}-{s[6:]}'  # noqa: E731
    expect = [
        f'{len(EVENTS)} 個事件日', f'{fmt(d0)} ～ {fmt(d1)}',
        f'有 {unparsed_sent} 個句子（共 {len(unparsed)} 種寫法）', f'分布在 {ev_with_null} 個已解析的事件',
        f'共 {noise} 句未收錄', f'{inline} 個事件無附件', f'有 {len(no_page)} 天只出現在前一天公告的「明天」中',
    ] + [f'{fmt(d)}' for d in no_page]
    probs = [f'README lacks: {x}' for x in expect if x not in text]
    return verdict('G11', probs, f'measured: events={len(EVENTS)} unparsed_sent={unparsed_sent}/{len(unparsed)} '
                   f'events_with_null={ev_with_null} noise={noise} inline={inline} no_own_page={len(no_page)}')


if __name__ == '__main__':
    cmds = {'coverage': coverage, 'cache-integrity': cache_integrity, 'header-date': header_date,
            'city-rows': city_rows, 'times': times, 'forecast': forecast, 'hygiene': hygiene, 'readme': readme}
    try:
        from audit_english import english  # noqa: F401  (added with G8)
        cmds['english'] = english
    except ImportError:
        pass
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit(f'usage: audit_full.py {{{"|".join(cmds)}}}')
    sys.exit(cmds[sys.argv[1]]() or 0)
