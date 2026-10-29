"""Daily public-site verification of one public Jeonbuk gosi list.

This independent, read-only PUBLIC adapter contains no private radar data/code,
tokens or internal review state. It only changes verified-notices.json when
all nine exact title queries and every published result page have been checked.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse
from zoneinfo import ZoneInfo

from scripts.check_public_release import validate

BASE = "https://www.jeonbuk.go.kr/board/list.jeonbuk"
BOARD_ID = "BBS_0000129"
MENU = "DOM_000000102002005000"
SOURCE = "S24_JEONBUK_GOSI"
TERMS = (
    "녹색건축", "녹색건축물", "녹색건축물 설계기준",
    "건축심의", "BF", "CPTED", "일조", "제로에너지", "건축물 에너지",
)
SINCE = "2026-01-01"
MAX_PAGES = 100
MAX_RECORDS = 1000
SUMMARY_RE = re.compile(r"총\s*([0-9,]+)\s*건\s*\(\s*([0-9]+)\s*/\s*([0-9]+)\s*페이지\s*\)")
DATE_RE = re.compile(r"20\d\d-[01]\d-[0-3]\d")
KST = ZoneInfo("Asia/Seoul")


class PageReader(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text = []
        self.keyword = None
        self.in_table = False
        self.in_body = False
        self.in_row = False
        self.in_cell = False
        self.cells = []
        self.cell_words = []
        self.cell_href = None
        self.rows = []
        self.in_page = False
        self.in_selected = False
        self.selected_words = []
        self.current_page = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name") == "keyword":
            self.keyword = a.get("value")
        if tag == "table" and "bbs_table" in (a.get("class") or "").split():
            self.in_table = True
        elif tag == "tbody" and self.in_table:
            self.in_body = True
        elif tag == "tr" and self.in_body:
            self.in_row, self.cells = True, []
        elif tag == "td" and self.in_row:
            self.in_cell, self.cell_words, self.cell_href = True, [], None
        elif tag == "a" and self.in_cell and a.get("href"):
            self.cell_href = a["href"]
        if tag == "p" and "bbs_page" in (a.get("class") or "").split():
            self.in_page = True
        if tag == "a" and self.in_page and "on" in (a.get("class") or "").split():
            self.in_selected, self.selected_words = True, []

    def handle_data(self, word):
        self.text.append(word)
        if self.in_cell:
            self.cell_words.append(word)
        if self.in_selected:
            self.selected_words.append(word)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_cell:
            self.cells.append((" ".join(" ".join(self.cell_words).split()), self.cell_href))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.cells:
                self.rows.append(self.cells)
            self.in_row = False
        elif tag == "tbody":
            self.in_body = False
        elif tag == "table" and self.in_table:
            self.in_table = False
        elif tag == "a" and self.in_selected:
            page = "".join(self.selected_words).strip()
            if page.isdigit():
                self.current_page = int(page)
            self.in_selected = False
        elif tag == "p" and self.in_page:
            self.in_page = False


def official_url(term, page):
    return BASE + "?" + urlencode({
        "boardId": BOARD_ID, "menuCd": MENU,
        "orderBy": "REGISTER_DATE:DESC,TMP_FIELD1:DESC",
        "paging": "ok", "listRow": "10",
        "searchType": "DATA_TITLE", "keyword": term,
        "startPage": str(page),
    })


def parse_official_page(html, url, term, page):
    u = urlparse(url)
    q = parse_qs(u.query)
    if (u.scheme != "https" or u.hostname != "www.jeonbuk.go.kr"
            or u.path != "/board/list.jeonbuk"
            or q.get("boardId") != [BOARD_ID]
            or q.get("searchType") != ["DATA_TITLE"]
            or q.get("keyword") != [term]
            or q.get("startPage") != [str(page)]):
        raise ValueError("Official returned query/page URL unverified")
    p = PageReader()
    p.feed(html)
    if p.keyword != term:
        raise ValueError("Official site did not display submitted keyword")
    match = SUMMARY_RE.search(" ".join(p.text))
    if match is None or p.current_page != page:
        raise ValueError("Official result count/page not confirmed")
    total, current, pages = (int(v.replace(",", "")) for v in match.groups())
    if current != page:
        raise ValueError("Official pagination mismatch")
    if total == 0 and pages == 0 and page == 1:
        pages = 1
    if pages < 1 or pages > MAX_PAGES or total < 0 or page > pages:
        raise ValueError("Official result count or page limit invalid")
    records = []
    for cells in p.rows:
        if len(cells) < 7:
            continue
        title, href = cells[3]
        if not title or not href:
            raise ValueError("Official listing title/detail link missing")
        full = urlparse(urljoin(BASE, href))
        params = parse_qs(full.query)
        sid = params.get("dataSid", [""])[0]
        if (full.scheme != "https" or full.hostname != "www.jeonbuk.go.kr"
                or full.path != "/board/view.jeonbuk"
                or params.get("boardId") != [BOARD_ID]
                or not sid.isdigit()):
            raise ValueError("Untrusted official document")
        published = cells[5][0]
        if not DATE_RE.fullmatch(published):
            raise ValueError("Official date missing")
        date.fromisoformat(published)
        records.append({
            "id": SOURCE + ":" + sid,
            "title": title[:500],
            "published_at": published,
            "notice_no": cells[2][0][:120],
            "url": ("https://www.jeonbuk.go.kr/board/view.jeonbuk?"
                    + urlencode({"boardId": BOARD_ID, "menuCd": MENU, "dataSid": sid})),
        })
    if total > 0 and not records:
        raise ValueError("Nonempty official results but no dated post rows")
    if total == 0 and records:
        raise ValueError("Zero official results with positive post rows")
    return total, pages, records


async def run_queries(request, *, since=SINCE, max_pages=MAX_PAGES, pause=0.5):
    all_records = {}
    diagnostics = []
    for term in TERMS:
        verified = 0
        official_total = None
        official_pages = None
        previous_ids = None
        for number in range(1, max_pages + 1):
            url = official_url(term, number)
            last_error = None
            for attempt in range(2):
                try:
                    response = await request.get(url, timeout=30000, max_redirects=2)
                    if response.status != 200:
                        raise ValueError(f"Official server returned HTTP {response.status}")
                    total, pages, rows = parse_official_page(
                        await response.text(), response.url, term, number)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt == 0:
                        await asyncio.sleep(1.5)
            if last_error:
                raise ValueError(f"{term}, official page {number} unverified: {last_error}")
            if official_pages is None:
                official_pages, official_total = pages, total
            if (pages, total) != (official_pages, official_total):
                raise ValueError("Official totals changed during pagination")
            ids = {r["id"] for r in rows}
            if previous_ids and ids == previous_ids:
                raise ValueError("Official pagination returned repeated items")
            previous_ids = ids
            for item in rows:
                if item["published_at"] < since:
                    continue
                old = all_records.get(item["id"])
                if old and old != item:
                    raise ValueError("Different metadata for same official item across keywords")
                all_records[item["id"]] = item
            verified += 1
            if verified >= official_pages:
                break
            if pause:
                await asyncio.sleep(pause)
        if verified != official_pages:
            raise ValueError(f"{term}: only {verified}/{official_pages} pages checked")
        diagnostics.append({
            "keyword": term, "official_total": official_total,
            "pages_verified": verified, "official_pages": official_pages,
        })
    if len(all_records) > MAX_RECORDS:
        raise ValueError("Too many published records for approved public schema")
    return sorted(all_records.values(), key=lambda r:(r["published_at"], r["id"]), reverse=True), diagnostics


def feed_from_records(records, checked_at):
    return {
        "schema_version": 1,
        "status": "verified",
        "source_id": SOURCE,
        "last_verified_kst": checked_at.isoformat(),
        "search_terms_verified": len(TERMS),
        "all_search_pages_verified": True,
        "notice_count": len(records),
        "records": records,
        "original_body_and_attachments_verified": False,
        "legal_changes_confirmed": False,
        "legacy_portal_snapshot_date": "2026-10-28",
    }


async def run(feed_path, audit_path):
    from playwright.async_api import async_playwright
    async with async_playwright() as p:
        request = await p.request.new_context(timeout=30000)
        try:
            records, diagnostic = await run_queries(request)
        finally:
            await request.dispose()
    checked = datetime.now(KST)
    new_data = feed_from_records(records, checked)
    validate(new_data)
    old = json.loads(feed_path.read_text(encoding="utf-8"))
    validate(old)
    old_ids = {r["id"] for r in old.get("records", [])}
    new_ids = {r["id"] for r in records}
    result = {
        "status": "fully_verified",
        "source": SOURCE,
        "checked_at_kst": checked.isoformat(),
        "keywords_checked": len(TERMS),
        "pages_checked": sum(x["pages_verified"] for x in diagnostic),
        "posted_count": len(records),
        "new_post_candidates_not_law_amendments": len(new_ids - old_ids),
        "no_longer_in_search_not_deleted": len(old_ids - new_ids),
        "terms": diagnostic,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n",encoding="utf-8")
    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=feed_path.parent,
                                     prefix=".verified-", suffix=".json",delete=False) as handle:
        json.dump(new_data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary=Path(handle.name)
    os.replace(temporary,feed_path)
    print(json.dumps({k:v for k,v in result.items() if k!="terms"},ensure_ascii=False))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--feed",type=Path,default=Path("verified-notices.json"))
    parser.add_argument("--audit",type=Path,default=Path("data/audit/official-daily.json"))
    args=parser.parse_args()
    try:
        asyncio.run(run(args.feed,args.audit))
    except Exception as exc:
        args.audit.parent.mkdir(parents=True,exist_ok=True)
        args.audit.write_text(json.dumps({
            "status":"failed_previous_verified_feed_preserved",
            "error":f"{type(exc).__name__}: {str(exc)[:320]}",
            "attempted_at_kst":datetime.now(KST).isoformat()
        },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        raise


if __name__=="__main__":
    main()
