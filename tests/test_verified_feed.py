import copy
import json
import unittest
from scripts.check_public_release import validate, validate_site, ROOT

def sample():
    return {
        "schema_version": 1,
        "status": "verified",
        "source_id": "S24_JEONBUK_GOSI",
        "last_verified_kst": "2026-10-29T13:54:00+09:00",
        "search_terms_verified": 9,
        "all_search_pages_verified": True,
        "notice_count": 1,
        "records": [{
            "id": "S24_JEONBUK_GOSI:655167",
            "title": "전북 녹색건축물 관련 공고",
            "published_at": "2026-03-26",
            "notice_no": "제2026-664호",
            "url": "https://www.jeonbuk.go.kr/board/view.jeonbuk?boardId=BBS_0000129&dataSid=655167"
        }],
        "original_body_and_attachments_verified": False,
        "legal_changes_confirmed": False,
        "legacy_portal_snapshot_date": "2026-10-28"
    }

class FeedTests(unittest.TestCase):
    def test_published_official_feed_matches_schema(self):
        status = validate_site(ROOT)
        self.assertTrue(status.startswith("verified_records:"), status)
        x=json.loads((ROOT/"verified-notices.json").read_text(encoding="utf-8"))
        self.assertEqual(status, f"verified_records:{x['notice_count']}")
        self.assertEqual(x["search_terms_verified"], 9)
        self.assertFalse(x["legal_changes_confirmed"])
        self.assertFalse(x["original_body_and_attachments_verified"])
    def test_strict_valid_example(self):
        self.assertEqual(validate(sample()), "verified_records:1")
    def test_disallowed_metadata(self):
        x=sample()
        x["extra_field"]="not-for-public"
        with self.assertRaises(ValueError):
            validate(x)
    def test_wrong_source_link(self):
        x=sample()
        x["records"][0]["url"]="https://example.org"
        with self.assertRaises(ValueError):
            validate(x)
    def test_incomplete_pages(self):
        x=sample()
        x["all_search_pages_verified"]=False
        with self.assertRaises(ValueError):
            validate(x)
    def test_unconnected_is_not_verified_zero(self):
        x={"schema_version":1,"status":"not_connected",
           "source_id":"S24_JEONBUK_GOSI","records":[],
           "notice_count":None,"all_search_pages_verified":False,
           "original_body_and_attachments_verified":False,
           "legal_changes_confirmed":False,
           "legacy_portal_snapshot_date":"2026-10-28"}
        self.assertEqual(validate(x), "not_connected")
        x["notice_count"]=0
        with self.assertRaises(ValueError):
            validate(x)
    def test_duplicate(self):
        x=sample()
        x["notice_count"]=2
        x["records"].append(copy.deepcopy(x["records"][0]))
        with self.assertRaises(ValueError):
            validate(x)
