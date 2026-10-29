import copy
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.sync_law_ordinances import (
    TERMS, SOURCE, query_url, parse_page, collect, validate_feed, atomic_publish
)


def xml(term="녹색건축", page=1, total=1, seq="2172937", title="녹색건축물 조성 지원 조례"):
    row = f"""<자치법규><자치법규일련번호>{seq}</자치법규일련번호>
    <자치법규명>{title}</자치법규명>
    <지자체기관명>세종특별자치시</지자체기관명>
    <공포일자>20260930</공포일자>
    <시행일자>20260930</시행일자>
    <자치법규종류>규칙</자치법규종류>
    <제개정구분명>일부개정</제개정구분명>
    <공포번호>409</공포번호></자치법규>""" if total else ""
    return f"<LawSearch><totalCnt>{total}</totalCnt><page>{page}</page>{row}</LawSearch>".encode()


class LawApiTests(unittest.TestCase):
    def test_query_scope(self):
        url = query_url("REDACTED", TERMS[0], 1, date(2026, 9, 1), date(2026, 10, 29))
        self.assertIn("ancYd=20260901~20261029", url)
        self.assertIn("target=ordin", url)
        self.assertIn("sort=ddes", url)

    def test_official_metadata(self):
        total, rows = parse_page(xml(), expected_page=1, start=date(2026, 9, 1), end=date(2026, 10, 29))
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], SOURCE + ":2172937")
        self.assertEqual(rows[0]["published_at"], "2026-09-30")
        self.assertEqual(rows[0]["url"], "https://www.law.go.kr/ordinInfoP.do?ordinSeq=2172937")

    def test_bad_page_and_bad_date_fail(self):
        with self.assertRaises(ValueError):
            parse_page(xml(), expected_page=2, start=date(2026, 9, 1), end=date(2026, 10, 29))
        with self.assertRaises(ValueError):
            parse_page(xml().replace(b"20260930", b"20250930"), expected_page=1,
                       start=date(2026, 9, 1), end=date(2026, 10, 29))

    def test_complete_queries_and_dedup(self):
        class Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return xml()
        feed, audit = collect(oc="secret", today=date(2026, 10, 29),
                              days=120, opener=lambda *a, **k: Resp(), delay=0)
        self.assertEqual(len(audit), len(TERMS))
        self.assertEqual(validate_feed(feed), 1)
        self.assertFalse(feed["legal_changes_confirmed"])

    def test_bad_source_and_link_rejected(self):
        class Resp:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, count): return xml()
        feed, _ = collect(oc="secret", today=date(2026, 10, 29),
                          opener=lambda *a, **k: Resp(), delay=0)
        altered = copy.deepcopy(feed)
        altered["records"][0]["url"] = "https://example.com"
        with self.assertRaises(ValueError):
            validate_feed(altered)
        with TemporaryDirectory() as d:
            dest = Path(d) / "out.json"
            with self.assertRaises(ValueError):
                atomic_publish(altered, dest)
            self.assertFalse(dest.exists())


if __name__ == "__main__":
    unittest.main()
