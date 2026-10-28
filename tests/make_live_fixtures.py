"""Regenerate tests/fixtures/live/*.json from the HTML pages next to them.

Usage: python3 tests/make_live_fixtures.py [pid ...]
Each pid is copied from .cache/ first (its Chinese attachment, as {date}-{pid}.html). Review the JSON diff
before committing: the JSON files are the contract that other parsers of nds.html are tested against.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import parse  # noqa: E402

DIR = ROOT / 'tests' / 'fixtures' / 'live'


def expected(html_bytes):
    page = parse.parse_page(parse.decode(html_bytes))
    del page['rows']
    return page


if __name__ == '__main__':
    meta = json.load(open(parse.CACHE / 'meta.json'))
    for pid in sys.argv[1:]:
        b = parse.pick_attachment(pid, meta[pid]).read_bytes()
        (DIR / f'{expected(b)["pageDate"]}-{pid}.html').write_bytes(b)
    for f in sorted(DIR.glob('*.html')):
        f.with_suffix('.json').write_text(
            json.dumps(expected(f.read_bytes()), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f.name)
