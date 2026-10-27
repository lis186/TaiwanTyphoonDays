"""Update .cache/all_items.json, a list of (pid, published, title), newest first.

Incremental: reads pages from the newest and stops at the first page that contains only known items, so a
normal day costs one request. The first run (no list yet) reads every page.
Exits non-zero unless the merged list matches the total the site states, so a bad crawl can never shrink it.
"""
import itertools
import json
import os
import re
import ssl
import sys
import time
import urllib.request

os.makedirs('.cache', exist_ok=True)
UA = {'User-Agent': 'Mozilla/5.0'}
URL = 'https://www.dgpa.gov.tw/informationlist?uid=374&page={}'
# dgpa.gov.tw's certificate lacks a Subject Key Identifier, which Python >= 3.13 rejects in strict mode.
# Chain and hostname verification stay on; only the strict X.509 profile check is dropped.
CTX = ssl.create_default_context()
CTX.verify_flags &= ~ssl.VERIFY_X509_STRICT
LIST = '.cache/all_items.json'


def get(u):
    for i in range(3):
        try:
            return urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30, context=CTX).read().decode('utf-8')
        except Exception:  # noqa: BLE001
            if i == 2:
                raise
            time.sleep(2)


known = [tuple(x) for x in json.load(open(LIST))] if os.path.exists(LIST) else []
known_pids = {x[0] for x in known}
new, total = [], None
for p in itertools.count(1):
    s = get(URL.format(p))
    got = re.findall(r'pid=(\d+)">\s*<dt>([\d.]+)</dt>\s*<dd>\s*<p>\s*([^<]+?)\s*</p>', s)
    if p == 1:
        m = re.search(r'共\s*<b>(\d+)</b>\s*筆', s)
        total = int(m.group(1)) if m else None
        open('.cache/list_page1.html', 'w', encoding='utf-8').write(s)
    fresh = [x for x in got if x[0] not in known_pids and x[0] not in {n[0] for n in new}]
    new += fresh
    if not got or (known_pids and len(fresh) < len(got)):
        break  # end of list, or reached items we already have
    time.sleep(0.3)

items = new + known
if total is None or len(items) != total or len({i[0] for i in items}) != len(items):
    sys.exit(f'list inconsistent: have {len(items)} (new {len(new)}), unique {len({i[0] for i in items})}, site total {total}')
json.dump(items, open(LIST, 'w'), ensure_ascii=False)
print(f'{len(items)} items, {len(new)} new (site total {total}), pages read: {p}')
