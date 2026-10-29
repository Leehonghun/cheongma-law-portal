"""Public-only feed validator: intentionally no private repository/API access."""
from __future__ import annotations
import json,re,sys
from pathlib import Path
from urllib.parse import urlparse,parse_qs
from datetime import datetime,date

ROOT=Path(__file__).resolve().parents[1]
ALLOWED_KEYS={
    "schema_version","status","source_id","message","last_verified_kst",
    "search_terms_verified","all_search_pages_verified","notice_count",
    "records","original_body_and_attachments_verified",
    "legal_changes_confirmed","legacy_portal_snapshot_date"}
ALLOWED_ITEM_KEYS={"id","title","published_at","notice_no","url"}
SOURCE="S24_JEONBUK_GOSI"

def validate(obj):
    if not isinstance(obj,dict) or set(obj)-ALLOWED_KEYS:
        raise ValueError("Private or unsupported feed fields are forbidden")
    if obj.get("schema_version")!=1 or obj.get("source_id")!=SOURCE:
        raise ValueError("Invalid official feed schema/source")
    if obj.get("legacy_portal_snapshot_date")!="2026-10-28":
        raise ValueError("Historical portal snapshot date changed")
    if obj.get("legal_changes_confirmed") is not False or obj.get("original_body_and_attachments_verified") is not False:
        raise ValueError("Unverified legal amendments/details must not be claimed")
    if obj.get("status")=="not_connected":
        if obj.get("records")!=[] or obj.get("notice_count") is not None or obj.get("all_search_pages_verified") is not False:
            raise ValueError("Unconnected feed cannot impersonate verified 0 results")
        return "not_connected"
    if obj.get("status")!="verified":
        raise ValueError("Unsupported feed status")
    if obj.get("search_terms_verified")!=9 or obj.get("all_search_pages_verified") is not True:
        raise ValueError("Must verify every configured term and page")
    checked=obj.get("last_verified_kst")
    if not isinstance(checked,str) or datetime.fromisoformat(checked).utcoffset() is None:
        raise ValueError("Verified timestamp must contain timezone")
    records=obj.get("records")
    if not isinstance(records,list) or not isinstance(obj.get("notice_count"),int):
        raise ValueError("Missing verified records/count")
    if len(records)!=obj["notice_count"] or len(records)>1000:
        raise ValueError("Result count inconsistency")
    seen=set()
    for x in records:
        if not isinstance(x,dict) or set(x)!=ALLOWED_ITEM_KEYS:
            raise ValueError("Record contains unapproved fields")
        sid=x.get("id")
        if not isinstance(sid,str) or not re.fullmatch(r"S24_JEONBUK_GOSI:[0-9]+",sid):
            raise ValueError("Not a trustworthy official notice ID")
        if sid in seen:raise ValueError("Duplicate official notice")
        seen.add(sid)
        title=x.get("title")
        if not isinstance(title,str) or not title.strip() or len(title)>500:
            raise ValueError("Missing/invalid title")
        published=x.get("published_at")
        if not isinstance(published,str) or not re.fullmatch(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}",published):
            raise ValueError("Invalid publication date")
        date.fromisoformat(published)
        if published<"2026-01-01":raise ValueError("Outside verified collection period")
        if not isinstance(x.get("notice_no"),str) or len(x["notice_no"])>120:
            raise ValueError("Invalid official notice number")
        u=urlparse(x.get("url",""))
        args=parse_qs(u.query)
        if (u.scheme!="https" or u.hostname!="www.jeonbuk.go.kr"
                or u.path!="/board/view.jeonbuk"
                or args.get("boardId")!=["BBS_0000129"]
                or args.get("dataSid")!=[sid.split(":")[1]]
                or u.username or u.password or u.fragment):
            raise ValueError("Untrusted original official detail link")
    return f"verified_records:{len(records)}"

def validate_site(root):
    html=(root/"index.html").read_text(encoding="utf-8")
    # The public dashboard must be institution-neutral; a pilot region cannot
    # create its own navigation/panel until a unified multi-source feed exists.
    if (html.count('id="intro-notice"') != 1
            or "2026년 10월 28일 수집 기준" not in html
            or "<!doctype html>" not in html.lower()
            or "verified-feed.js" in html
            or "verified-feed.css" in html
            or "cheongma-verified-feed" in html):
        raise ValueError("Legacy dashboard changed or region-only panel reintroduced")
    # Preserve the verified pilot JSON as data, but do not display it separately.
    # This does not mean all local government sources are live.
    return validate(json.loads((root/"verified-notices.json").read_text(encoding="utf-8")))

if __name__=="__main__":
    print(validate_site(ROOT))
