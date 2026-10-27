import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'scripts'))
import parse  # noqa: E402

D = datetime.date(2026, 10, 23)


def run(sent):
    """-> list of (scope, forDate YYYYMMDD, work, school, period, from) or None."""
    res = parse.parse_sentence(sent, D)
    return None if res is None else [(sc, fd.strftime('%Y%m%d'), w, s, p, f) for sc, fd, w, s, p, f in res]


T = '20261023'
N = '20261024'

CASES = [
    # whole-city, plain
    ('今天停止上班、停止上課。', [('', T, 'stop', 'stop', 'allDay', '')]),
    ('今天停止辦公、停止上課。', [('', T, 'stop', 'stop', 'allDay', '')]),
    ('今天照常上班、停止上課。', [('', T, 'normal', 'stop', 'allDay', '')]),
    ('今天已達停止上班及上課標準。', [('', T, 'stop', 'stop', 'allDay', '')]),
    ('今天未達停止上班及上課標準。', [('', T, 'normal', 'normal', 'allDay', '')]),
    ('今天未達停止上班、已達停止上課標準。', [('', T, 'normal', 'stop', 'allDay', '')]),
    ('今天停止上班上課', [('', T, 'stop', 'stop', 'allDay', '')]),
    # tomorrow -> forDate +1
    ('明天停止上班、停止上課。', [('', N, 'stop', 'stop', 'allDay', '')]),
    # scope
    ('旗山區:今天停止上班、停止上課。', [('旗山區', T, 'stop', 'stop', 'allDay', '')]),
    ('旗山區：今天停止上班、停止上課。', [('旗山區', T, 'stop', 'stop', 'allDay', '')]),
    ('恆春鎮今天停止辦公、停止上課。', [('恆春鎮', T, 'stop', 'stop', 'allDay', '')]),
    # periods and times (12h -> 24h)
    ('今天下午停止上班、停止上課。', [('', T, 'stop', 'stop', 'afternoon', '')]),
    ('今天晚上已達停止上班及上課標準。', [('', T, 'stop', 'stop', 'evening', '')]),
    ('今天上午停止辦公、停止上課。', [('', T, 'stop', 'stop', 'morning', '')]),
    ('今天中午12:00起停止上班、停止上課。', [('', T, 'stop', 'stop', 'from', '12:00')]),
    ('今天下午01:00起停止上班、停止上課。', [('', T, 'stop', 'stop', 'from', '13:00')]),
    ('今天晚上6:00起停止上班、停止上課。', [('', T, 'stop', 'stop', 'from', '18:00')]),
    ('今天下午4時30分起停止辦公、停止上課。', [('', T, 'stop', 'stop', 'from', '16:30')]),
    ('今天上午9時起停止上班、停止上課。', [('', T, 'stop', 'stop', 'from', '09:00')]),
    ('和平區：今天中午12:00起，停止上班、停止上課。', [('和平區', T, 'stop', 'stop', 'from', '12:00')]),
    # compound periods split into several records
    ('今天下午及晚上停止辦公、停止上課。',
     [('', T, 'stop', 'stop', 'afternoon', ''), ('', T, 'stop', 'stop', 'evening', '')]),
    ('今天上午、下午停止辦公、停止上課。',
     [('', T, 'stop', 'stop', 'morning', ''), ('', T, 'stop', 'stop', 'afternoon', '')]),
    ('今天上午已達停止上班及上課標準 ，下午未達停止上班及上課標準。',
     [('', T, 'stop', 'stop', 'morning', ''), ('', T, 'normal', 'normal', 'afternoon', '')]),
    # partial school levels
    ('今天照常辦公、高中及高中以下停止上課。', [('', T, 'normal', 'partial', 'allDay', '')]),
    ('今天照常辦公、國中以下停止上課。', [('', T, 'normal', 'partial', 'allDay', '')]),
    # trailing remark is ignored for the status, kept in raw
    ('今天下午已達停止辦公及上課標準(上午未達)。', [('', T, 'stop', 'stop', 'afternoon', '')]),
]

# Regression: sentences that used to be parsed wrongly, or that are ambiguous. Must stay unparsed.
MUST_BE_UNPARSED = [
    '今天停止上課、下午停止辦公。',  # mixed periods per field
    '三星鄉:今天停止上課、下午停止辦公。',
    '今天照常辦公、下午高中及高中以下停止上課。',  # period applies to school only
    '今日停止上班上課 美濃區美濃國小:停止上課、照常上班',  # two sentences glued together
    '花蓮縣秀林鄉天祥地區今天十點起: 今天已達停止上班及上課標準。',  # Chinese-numeral time in scope
    '今天晚上06:00前停止上班、停止上課。',  # "until", not representable
    '今天下午（含晚上）停止辦公、停止上課。',
    '今天下午3時後（含晚上）停止辦公、停止上課。',
    '尚未列入警戒區。',
    '（下午 4時後停止辦公上課）',
]


class ParseSentence(unittest.TestCase):
    def test_cases(self):
        for sent, expected in CASES:
            with self.subTest(sent):
                self.assertEqual(run(sent), expected)

    def test_must_be_unparsed(self):
        for sent in MUST_BE_UNPARSED:
            with self.subTest(sent):
                self.assertIsNone(run(sent))


class Helpers(unittest.TestCase):
    def test_norm_city(self):
        self.assertEqual(parse.norm_city('台北巿'), '臺北市')
        self.assertEqual(parse.norm_city('新北市'), '新北市')

    def test_roc_to_ad(self):
        self.assertEqual(parse.roc_to_ad(('115', '10', '24')), datetime.date(2026, 10, 24))
        self.assertEqual(parse.roc_to_ad(('90', '9', '27')), datetime.date(2001, 9, 27))

    def test_parse_updated(self):
        self.assertEqual(parse.parse_updated('更新時間：2026/10/24 00:09:41'), '2026-10-24T00:09:41')
        self.assertEqual(parse.parse_updated('更新時間： 102/10/07 08:07:06'), '2013-10-07T08:07:06')
        self.assertEqual(parse.parse_updated('更新時間： 90/09/27 '), '2001-09-27')
        self.assertEqual(parse.parse_updated('沒有'), '')


if __name__ == '__main__':
    unittest.main()
