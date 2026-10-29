import unittest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import AsyncMock

from scripts.sync_public_official_notices import (
    parse_official_page, official_url, feed_from_records,
    run_queries, TERMS, SOURCE,
)
from scripts.check_public_release import validate


def sample_html(term, page=1, pages=1, total=1, data_id=655167, when="2026-03-26"):
    row = (
        '<table class="bbs_table"><tbody><tr>'
        '<td>1</td><td>공고</td><td>2026-664</td>'
        '<td><a href="/board/view.jeonbuk?boardId=BBS_0000129'
        '&amp;dataSid='+str(data_id)+'">전북 녹색건축물 관련 공고</a></td>'
        '<td>주택건축과</td><td>'+when+'</td><td>250</td>'
        '</tr></tbody></table>'
    ) if total else '<table class="bbs_table"><tbody></tbody></table>'
    return ('<form><input name="keyword" value="'+term+'"></form>'
            '<div>총 '+str(total)+' 건( '+str(page)+' /'
            +str(pages)+' 페이지)</div>'
            +row+'<p class="bbs_page"><a class="on">'+str(page)+'</a></p>')


class OfficialPageTests(unittest.TestCase):
    def test_real_official_link_and_date(self):
        total,pages,records=parse_official_page(sample_html(TERMS[0]),official_url(TERMS[0],1),TERMS[0],1)
        self.assertEqual((total,pages), (1,1))
        self.assertEqual(records[0]["id"], SOURCE+":655167")
        self.assertEqual(records[0]["published_at"],"2026-03-26")
        self.assertEqual(set(records[0]),{"id","title","published_at","notice_no","url"})
    def test_zero_result_official_sentinel(self):
        total,pages,items=parse_official_page(sample_html(TERMS[0],total=0,pages=0),official_url(TERMS[0],1),TERMS[0],1)
        self.assertEqual((total,pages,len(items)),(0,1,0))
    def test_wrong_query_page_fails_closed(self):
        with self.assertRaises(ValueError):
            parse_official_page(sample_html(TERMS[0]),official_url(TERMS[0],2),TERMS[0],1)
        with self.assertRaises(ValueError):
            parse_official_page(sample_html("제로에너지"),official_url(TERMS[0],1),TERMS[0],1)
    def test_nonempty_but_no_dated_rows_rejected(self):
        with self.assertRaises(ValueError):
            parse_official_page(sample_html(TERMS[0]).replace('class="bbs_table"','class="untrusted"'),
                                official_url(TERMS[0],1),TERMS[0],1)
    def test_public_feed_passes_strict_allowlist(self):
        record=parse_official_page(sample_html(TERMS[0]),official_url(TERMS[0],1),TERMS[0],1)[2]
        f=feed_from_records(record,datetime(2026,10,29,18,0,tzinfo=ZoneInfo("Asia/Seoul")))
        self.assertEqual(validate(f),"verified_records:1")
        self.assertEqual(f["source_id"],SOURCE)


class AllQueriesTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_nine_official_queries_and_identity_dedup(self):
        class Reply:
            status=200
            def __init__(self,url,term):self.url=url;self.term=term
            async def text(self):return sample_html(self.term)
        class FakeRequest:
            async def get(self,url,**kwargs):
                from urllib.parse import parse_qs,urlparse
                term=parse_qs(urlparse(url).query)["keyword"][0]
                return Reply(url,term)
        records,diag=await run_queries(FakeRequest(),pause=0)
        self.assertEqual(len(diag),9)
        self.assertEqual(len(records),1)
        self.assertEqual(sum(x["pages_verified"] for x in diag),9)

    async def test_incomplete_first_page_throws_not_marks_success(self):
        class Fail:
            async def get(self,url,**kwargs):raise TimeoutError("official server timeout")
        with self.assertRaises(ValueError):
            await run_queries(Fail(),pause=0)
