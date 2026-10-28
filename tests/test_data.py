"""Invariants on data/*.json. Cache-free tests always run; the audit needs .cache/ and is skipped without it."""
import datetime
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit  # noqa: E402

HERE = Path(__file__).resolve().parent
EVENTS = audit.load_events()
AREAS = [(e, a) for e in EVENTS for a in e['areas']]
ymd = lambda s: datetime.datetime.strptime(s, '%Y%m%d').date()  # noqa: E731


class Schema(unittest.TestCase):
    def test_events_sorted_and_in_right_year_file(self):
        for f in sorted((audit.ROOT / 'data').glob('*.json')):
            import json
            evs = json.loads(f.read_text(encoding='utf-8'))
            dates = [e['date'] for e in evs]
            self.assertEqual(dates, sorted(dates), f.name)
            self.assertTrue(all(d.startswith(f.stem) for d in dates), f.name)

    def test_one_file_per_year_without_gaps(self):
        years = sorted(int(f.stem) for f in (audit.ROOT / 'data').glob('*.json'))
        self.assertEqual(years, list(range(2001, years[-1] + 1)))

    def test_event_fields(self):
        for e in EVENTS:
            self.assertEqual(set(e), {'date', 'publishedAt', 'updatedAt', 'sourceUrl', 'parsed', 'areas'})
            ymd(e['date'])
            self.assertGreaterEqual(ymd(e['publishedAt']), ymd(e['date']), e['sourceUrl'])
            self.assertRegex(e['updatedAt'], r'^$|^\d{4}-\d\d-\d\d(T\d\d:\d\d:\d\d)?$')
            self.assertIsInstance(e['parsed'], bool)

    def test_unique_dates(self):
        dates = [e['date'] for e in EVENTS]
        self.assertEqual(len(dates), len(set(dates)))

    def test_area_values(self):
        for e, a in AREAS:
            tag = (e['date'], a['raw'][:30])
            self.assertEqual(set(a), {'city', 'scope', 'forDate', 'work', 'school', 'period', 'from', 'raw'}, tag)
            self.assertIn(a['work'], ('stop', 'normal', None), tag)
            self.assertIn(a['school'], ('stop', 'normal', 'partial', None), tag)
            self.assertIn(a['period'], ('allDay', 'morning', 'afternoon', 'evening', 'from', None), tag)
            self.assertIn((ymd(a['forDate']) - ymd(e['date'])).days, (0, 1), tag)
            self.assertTrue(a['raw'], tag)
            # unparsed iff all three status fields are null
            nulls = [a['work'] is None, a['school'] is None, a['period'] is None]
            self.assertIn(sum(nulls), (0, 3), tag)

    def test_from_matches_period(self):
        for e, a in AREAS:
            if a['period'] == 'from':
                self.assertRegex(a['from'], r'^([01]\d|2[0-3]):[0-5]\d$', a['raw'])
            else:
                self.assertEqual(a['from'], '', a['raw'])

    def test_partial_school_mentions_level(self):
        for e, a in AREAS:
            if a['school'] == 'partial':
                self.assertRegex(a['raw'], '以下')

    def test_city_names_are_normalised(self):
        for e, a in AREAS:
            if e['parsed']:
                self.assertNotIn('巿', a['city'])
                self.assertNotIn('台', a['city'])

    def test_unparsed_events_have_single_raw_area(self):
        for e in EVENTS:
            if not e['parsed']:
                self.assertEqual(len(e['areas']), 1, e['sourceUrl'])
                self.assertIsNone(e['areas'][0]['work'])
                a = e['areas'][0]
                if a['city']:  # a city is only given when the text is about that city alone
                    self.assertTrue(a['raw'].startswith(a['city']), e['sourceUrl'])


class FormatDrift(unittest.TestCase):
    """The yearly canary: a sentence the parser cannot read must be reviewed by a human.

    If this fails after an update, look at the listed sentences. Extend parse.py if they are a
    new format worth supporting, or append them to tests/known_unparsed.txt to accept them as raw.
    """

    def test_no_new_unparsed_sentences(self):
        known = set((HERE / 'known_unparsed.txt').read_text(encoding='utf-8').splitlines())
        found = {a['raw'].strip() for e in EVENTS if e['parsed'] for a in e['areas'] if a['work'] is None}
        self.assertEqual(sorted(found - known), [], 'new unparsed sentences; review them')

    def test_known_unparsed_not_stale(self):
        known = set((HERE / 'known_unparsed.txt').read_text(encoding='utf-8').splitlines())
        found = {a['raw'].strip() for e in EVENTS if e['parsed'] for a in e['areas'] if a['work'] is None}
        self.assertEqual(sorted(known - found), [], 'known_unparsed.txt lists sentences no longer unparsed')


@unittest.skipUnless((audit.parse.CACHE / 'meta.json').exists(), 'needs .cache/ (run scripts/fetch_all.py)')
class AuditAgainstCache(unittest.TestCase):
    def test_audit(self):
        problems = audit.run_all()
        for name, items in problems.items():
            with self.subTest(name):
                self.assertEqual(items, [], f'{name}: {len(items)} problems, first: {items[:3]}')


if __name__ == '__main__':
    unittest.main()
