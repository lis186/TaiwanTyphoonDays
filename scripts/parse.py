"""Parse cached DGPA announcements (.cache/) into data/{year}.json.

Usage: python3 scripts/parse.py [--report]
"""
import collections
import datetime
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / '.cache'
SOURCE = 'https://www.dgpa.gov.tw/information?uid=374&pid='
NOT_CHINESE_ATT = re.compile(r'english|ndse|_e\.html|英文|^2\b', re.I)
CITY_RE = re.compile(r'^[一-鿿]{2,3}[縣市巿]$')
NOISE = re.compile(r'^[（(]?(?:尚未列入警戒區|尚未宣布消息)')
PERIODS = {'上午': 'morning', '下午': 'afternoon', '晚上': 'evening'}


def decode(b):
    for enc in ('utf-8', 'big5', 'cp950'):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            pass
    return b.decode('big5', 'replace')


def clean(x):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', x))).strip()


def norm_city(c):
    return c.replace('巿', '市').replace('台', '臺')


def roc_to_ad(s):
    y, m, d = (int(x) for x in s)
    return datetime.date(y + 1911 if y < 1911 else y, m, d)


def parse_updated(s):
    m = re.search(r'更新時間：\s*(\d+)/(\d+)/(\d+)(?:\s+(\d+:\d+:\d+))?', s)
    if not m:
        return ''
    d = roc_to_ad(m.groups()[:3]).isoformat()
    return f'{d}T{m.group(4)}' if m.group(4) else d


def classify(seg):
    if re.search(r'未達|照常', seg):
        return 'normal'
    if '高中' in seg and '停止' in seg:
        return 'partial'
    if re.search(r'已達|停止', seg):
        return 'stop'
    return None


def parse_status(rest):
    segs = [x for x in re.split(r'、', rest.strip('。 ，')) if x]
    if len(segs) == 1:
        v = classify(segs[0])
        both = re.search(r'上班|辦公', segs[0]) and '上課' in segs[0]
        return (v, v) if v and both else (None, None)
    if len(segs) == 2:
        w, s = classify(segs[0]), classify(segs[1])
        return (w, s) if w and s else (None, None)
    return None, None


def parse_time(prefix):
    """prefix like '下午01:00起' / '晚上6:00起' / '下午4時起' -> (period, from) or None."""
    m = re.match(r'(上午|中午|下午|晚上)?(\d{1,2})(?::(\d{2})|時(?:(\d{1,2})分)?)(起|前)', prefix)
    if not m:
        return None
    ap, h, mi, tail = m.group(1), int(m.group(2)), int(m.group(3) or m.group(4) or 0), m.group(5)
    if tail == '前':
        return 'until', None
    if ap in ('下午', '晚上') and h < 12:
        h += 12
    return 'from', f'{h:02d}:{mi:02d}'


def parse_sentence(sent, date):
    """One sentence -> list of (scope, forDate, work, school, period, from); None if unparseable."""
    sent = re.sub(r'\s+', '', sent)
    m = re.search(r'今天|今日|明天', sent)
    if m:
        scope = sent[:m.start()].rstrip(':：、')
        for_date = date + datetime.timedelta(days=1 if m.group() == '明天' else 0)
        rest = sent[m.end():]
    elif re.match(r'(上午|中午|下午|晚上)', sent):
        scope, for_date, rest = '', date, sent
    else:
        return None
    # compound: 上午已達...，下午未達... -> split on ，before a period word
    parts = re.split(r'，(?=(?:上午|中午|下午|晚上))', rest)
    out = []
    for part in parts:
        part = re.sub(r'(起|前)，', r'\1', part).replace('，', '、')
        t = parse_time(part)
        if t:
            period, frm = t
            if period == 'until':
                return None
            status = re.sub(r'^(上午|中午|下午|晚上)?\d{1,2}(?::\d{2}|時)起', '', part)
            work, school = parse_status(status)
            out.append((scope, for_date, work, school, period, frm))
            continue
        m = re.match(r'^((?:上午|中午|下午|晚上)(?:及(?:上午|中午|下午|晚上))*)', part)
        if m:
            status = part[m.end():]
            work, school = parse_status(status)
            for p in re.findall(r'上午|中午|下午|晚上', m.group(1)):
                if p == '中午':
                    return None
                out.append((scope, for_date, work, school, PERIODS[p], ''))
            continue
        work, school = parse_status(part)
        out.append((scope, for_date, work, school, 'allDay', ''))
    if any(w is None for _, _, w, _, _, _ in out):
        return None
    return out


def parse_cell(city, text, date, stats):
    areas = []
    for sent in re.split(r'(?<=[。；])', text):
        if not sent.strip():
            continue
        if NOISE.match(sent.strip()):
            stats['dropped'] += 1
            continue
        res = parse_sentence(sent, date)
        if res is None:
            stats['unparsed'][sent.strip()] += 1
            areas.append(dict(city=city, scope='', forDate=date.strftime('%Y%m%d'),
                              work=None, school=None, period=None, **{'from': ''}, raw=sent.strip()))
            continue
        for scope, fd, w, s, p, frm in res:
            areas.append(dict(city=city, scope=scope, forDate=fd.strftime('%Y%m%d'),
                              work=w, school=s, period=p, **{'from': frm}, raw=sent.strip()))
    return areas


def pick_attachment(pid, links):
    for i, (_, title) in enumerate(links):
        if not NOT_CHINESE_ATT.search(title):
            return CACHE / f'{pid}.att{i}'
    return CACHE / f'{pid}.att0' if links else None


def main():
    report = '--report' in sys.argv
    items = json.load(open(CACHE / 'all_items.json'))
    meta = json.load(open(CACHE / 'meta.json'))
    stats = dict(unparsed=collections.Counter(), noatt=[], norows=[], events=0, dropped=0)
    by_year = collections.defaultdict(dict)
    for pid, pub, title in items:
        m = re.match(r'(\d+)年(\d+)月(\d+)日', title)
        date = roc_to_ad(m.groups())
        pub_ad = roc_to_ad(pub.split('.')).strftime('%Y%m%d')
        ev = dict(date=date.strftime('%Y%m%d'), publishedAt=pub_ad, updatedAt='',
                  sourceUrl=SOURCE + pid, parsed=True, areas=[])
        att = pick_attachment(pid, meta[pid])
        if att is None:
            # inline free text on the detail page
            d = decode((CACHE / f'{pid}.detail').read_bytes())
            ed = re.search(r'<div id="editor">(.*?)<!-- download -->', d, re.S)
            body = clean(ed.group(1)) if ed else ''
            body = re.sub(r'^.*?公告時間：\s*[\d.]+\s*', '', body)
            cm = re.match(r'([一-鿿]{2,3}[縣市巿])', body)
            ev['parsed'] = False
            ev['areas'] = [dict(city=norm_city(cm.group(1)) if cm else '', scope='', forDate=ev['date'],
                                work=None, school=None, period=None, **{'from': ''}, raw=body)]
            stats['noatt'].append(pid)
        else:
            s = decode(att.read_bytes())
            ev['updatedAt'] = parse_updated(s)
            rows_seen = 0
            for tr in re.findall(r'<tr[^>]*>(.*?)</tr>', s, re.S | re.I):
                cells = [clean(c) for c in re.findall(r'<t[dh][^>]*>(.*?)</t[dh]>', tr, re.S | re.I)]
                if len(cells) not in (2, 3) or not CITY_RE.match(cells[-2]) or '名稱' in cells[-2]:
                    continue
                rows_seen += 1
                ev['areas'] += parse_cell(norm_city(cells[-2]), cells[-1], date, stats)
            if not rows_seen:
                ev['parsed'] = False
                stats['norows'].append(pid)
        stats['events'] += 1
        year = ev['date'][:4]
        if ev['date'] in by_year[year]:
            print('DUPLICATE DATE', ev['date'], pid, file=sys.stderr)
        by_year[year].setdefault(ev['date'], []).append(ev)

    out_dir = ROOT / 'data'
    out_dir.mkdir(exist_ok=True)
    for year, days in by_year.items():
        events = []
        for d in sorted(days):
            events += sorted(days[d], key=lambda e: e['updatedAt'])
        (out_dir / f'{year}.json').write_text(
            json.dumps(events, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('events', stats['events'], 'years', len(by_year),
          'no-attachment', len(stats['noatt']), 'no-rows', stats['norows'],
          'dropped-noise', stats['dropped'], 'unparsed sentences', sum(stats['unparsed'].values()), 'distinct', len(stats['unparsed']))
    if report:
        for s, n in stats['unparsed'].most_common():
            print(n, s)


if __name__ == '__main__':
    main()
