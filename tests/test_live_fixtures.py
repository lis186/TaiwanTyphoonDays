"""tests/fixtures/live/: page-level contract for parsers of nds.html (see the README there)."""
import collections
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit  # noqa: E402
import make_live_fixtures as mk  # noqa: E402

PAGES = sorted(mk.DIR.glob('*.html'))
EXPECTED = {f.stem: json.loads(f.with_suffix('.json').read_text(encoding='utf-8')) for f in PAGES}
EVENTS = {e['sourceUrl'].rsplit('=', 1)[1]: e for e in audit.load_events()}


def features(page):
    A, out = page['areas'], set()
    if page['noticeNone']:
        out.add('noticeNone')
    if not A and not page['noticeNone']:
        out.add('onlyNoise')
    if len({a['city'] for a in A}) >= 3:
        out.add('multiCity')
    whole = collections.defaultdict(set)
    for a in A:
        whole[a['city']].add(a['scope'] == '')
        out.add(a['period'] or 'unparsed')
        if (a['work'], a['school']) == ('normal', 'stop'):
            out.add('normalWorkStopSchool')
        if '、' in a['scope']:
            out.add('scopeList')
    if any(v == {True, False} for v in whole.values()):
        out.add('cityAndSubareaRows')
    if len({a['forDate'] for a in A}) > 1:
        out.add('todayAndTomorrow')
    return out


class LiveFixtures(unittest.TestCase):
    def test_json_matches_parser(self):
        for f in PAGES:
            self.assertEqual(mk.expected(f.read_bytes()), EXPECTED[f.stem], f'{f.name}: run tests/make_live_fixtures.py')

    def test_archived_pages_match_data(self):
        for stem, page in EXPECTED.items():
            pid = stem.split('-')[1]
            if pid == 'live':
                continue
            ev = EVENTS[pid]
            self.assertEqual((page['pageDate'], page['updatedAt'], page['areas']),
                             (ev['date'], ev['updatedAt'], ev['areas']), stem)

    def test_coverage(self):
        want = {'noticeNone', 'onlyNoise', 'multiCity', 'cityAndSubareaRows', 'scopeList', 'todayAndTomorrow',
                'allDay', 'morning', 'afternoon', 'evening', 'from', 'normalWorkStopSchool', 'unparsed'}
        got = set().union(*(features(p) for p in EXPECTED.values()))
        self.assertEqual(want - got, set())


if __name__ == '__main__':
    unittest.main()
