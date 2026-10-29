"""Read-only LAW OPEN DATA adapter: ordinance/rule/notice metadata candidates.

Only a fully verified response is published. A missing LAW_OC never counts
as zero results. Details, attachment contents and legal impacts are unverified.
Official API: https://open.law.go.kr/LSO/openApi/guideResult.do?htmlName=ordinListGuide
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ENDPOINT = "https://www.law.go.kr/DRF/lawSearch.do"
SOURCE = "LAW_ORDIN_2026"
# Targeted title terms, not a claim of full national legal coverage.
TERMS = ("녹색건축", "건축물 에너지", "제로에너지", "에너지절약", "친환경주택", "장수명주택")
MAX_PAGES = 30
PAGE_SIZE = 100
KST = ZoneInfo("Asia/Seoul")


def query_url(oc: str, term: str, page: int, start: date, end: date) -> str:
    if not oc or page < 1 or term not in TERMS:
        raise ValueError("Missing authentication or invalid query")
    args = {
        "OC": oc, "target": "ordin", "type": "XML", "nw": "1",
        "search": "1", "query": term, "sort": "ddes",
        "display": str(PAGE_SIZE), "page": str(page),
        "ancYd": f"{start:%Y%m%d}~{end:%Y%m%d}",
    }
    return ENDPOINT + "?" + urllib.parse.urlencode(args)


def normalized_date(raw: str) -> str:
    digits = re.sub(r"[-.\s]", "", (raw or "").strip())
    if not re.fullmatch(r"20\d{6}", digits):
        raise ValueError("Invalid official promulgation date")
    return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:]}").isoformat()


def parse_page(body: bytes, *, expected_page: int, start: date, end: date):
    if len(body) > 4_000_000:
        raise ValueError("Unexpectedly large API response")
    root = ET.fromstring(body)
    if root.find("totalCnt") is None or root.find("page") is None:
        raise ValueError("Missing official API pagination markers")
    total = int(root.findtext("totalCnt", "-1"))
    page = int(root.findtext("page", "-1"))
    if total < 0 or page != expected_page:
        raise ValueError("Official API page mismatch")
    items = root.findall(".//자치법규")
    if total > 0 and not items:
        raise ValueError("Nonempty response has no ordinance rows")
    if len(items) > PAGE_SIZE:
        raise ValueError("Page larger than requested")
    if expected_page > 1 and total <= (expected_page - 1) * PAGE_SIZE:
        raise ValueError("Unexpected empty trailing page")
    records = []
    for item in items:
        def get(k):
            return (item.findtext(k) or "").strip()
        seq, title, org = get("자치법규일련번호"), get("자치법규명"), get("지자체기관명")
        if not seq.isdigit() or not title or not org:
            raise ValueError("Official ordinance ID/title/institution missing")
        published = normalized_date(get("공포일자"))
        if not start.isoformat() <= published <= end.isoformat():
            raise ValueError("Official result outside requested date scope")
        records.append({
            "id": SOURCE + ":" + seq,
            "title": title[:400],
            "published_at": published,
            "effective_at": normalized_date(get("시행일자")) if get("시행일자") else None,
            "institution": org[:120],
            "document_type": get("자치법규종류")[:60],
            "revision_type": get("제개정구분명")[:60],
            "notice_no": get("공포번호")[:80],
            "url": "https://www.law.go.kr/ordinInfoP.do?ordinSeq=" + seq,
        })
    return total, records


def collect(*, oc: str, today: date | None = None, days: int = 120, opener=None, delay=0.2):
    if not oc.strip():
        raise ValueError("LAW_OC is not configured")
    today = today or datetime.now(KST).date()
    start = today - timedelta(days=days)
    opener = opener or urllib.request.urlopen
    found, audits = {}, []
    for term in TERMS:
        total = None
        pages = None
        seen_ids = set()
        for page in range(1, MAX_PAGES + 1):
            url = query_url(oc, term, page, start, today)
            # Key must never be logged or included in published audit files.
            with opener(urllib.request.Request(url, headers={"User-Agent": "LawRadarPilot/1.0"}), timeout=25) as response:
                if response.status != 200:
                    raise ValueError("Official API HTTP status not 200")
                raw = response.read(4_000_001)
            count, rows = parse_page(raw, expected_page=page, start=start, end=today)
            if total is None:
                total = count
                pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
                if pages > MAX_PAGES:
                    raise ValueError("Search scope exceeds safe page cap")
            elif count != total:
                raise ValueError("API result count changed during pagination")
            row_ids = {r["id"] for r in rows}
            if seen_ids & row_ids:
                raise ValueError("Duplicate official page results")
            seen_ids.update(row_ids)
            for row in rows:
                old = found.get(row["id"])
                if old is not None and old != row:
                    raise ValueError("Inconsistent metadata across queries")
                found[row["id"]] = row
            if page == pages:
                break
            if delay:
                time.sleep(delay)
        if len(seen_ids) != total:
            raise ValueError("Pagination item count mismatch")
        audits.append({"term": term, "total": total, "pages": pages, "verified": True})
    return {
        "schema_version": 1,
        "status": "verified",
        "source_id": SOURCE,
        "last_verified_kst": datetime.now(KST).isoformat(),
        "scope_start": start.isoformat(),
        "scope_end": today.isoformat(),
        "terms_verified": list(TERMS),
        "records": sorted(found.values(), key=lambda r: (r["published_at"], r["id"]), reverse=True),
        "original_body_and_attachments_verified": False,
        "legal_changes_confirmed": False,
    }, audits


def validate_feed(feed):
    if feed.get("schema_version") != 1 or feed.get("source_id") != SOURCE:
        raise ValueError("Bad API feed source/schema")
    if feed.get("status") != "verified":
        raise ValueError("Only verified feeds can be published")
    if feed.get("terms_verified") != list(TERMS):
        raise ValueError("Partial query scope")
    if datetime.fromisoformat(feed["last_verified_kst"]).utcoffset() is None:
        raise ValueError("Missing verified timezone")
    if feed.get("legal_changes_confirmed") is not False or feed.get("original_body_and_attachments_verified") is not False:
        raise ValueError("Unsupported legal change/details claim")
    start, end = date.fromisoformat(feed["scope_start"]), date.fromisoformat(feed["scope_end"])
    keys = set()
    for r in feed["records"]:
        if set(r) != {"id", "title", "published_at", "effective_at", "institution", "document_type", "revision_type", "notice_no", "url"}:
            raise ValueError("Bad public row fields")
        if not re.fullmatch(r"LAW_ORDIN_2026:\d+", r["id"]) or r["id"] in keys:
            raise ValueError("Duplicate or invalid ordinance ID")
        keys.add(r["id"])
        if not r["title"] or not r["institution"] or not start <= date.fromisoformat(r["published_at"]) <= end:
            raise ValueError("Bad metadata/date")
        seq = r["id"].split(":")[1]
        if r["url"] != "https://www.law.go.kr/ordinInfoP.do?ordinSeq=" + seq:
            raise ValueError("Unsupported detail link")
    return len(keys)


def atomic_publish(feed, path: Path):
    validate_feed(feed)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=".ordin-", delete=False) as handle:
        json.dump(feed, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def main():
    key = os.environ.get("LAW_OC", "").strip()
    if not key:
        print("LAW_OC missing: API feed preserved; NOT checked, NOT zero results")
        return
    feed, audits = collect(oc=key)
    atomic_publish(feed, Path("verified-ordinances.json"))
    print(json.dumps({
        "status": "verified", "source": SOURCE,
        "terms": len(audits), "records": len(feed["records"]),
        "scope_start": feed["scope_start"], "scope_end": feed["scope_end"]
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
