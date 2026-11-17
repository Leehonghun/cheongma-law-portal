"""Read-only LIVE browser verification of the public law-radar site."""
import os
from playwright.sync_api import sync_playwright

URL=os.environ.get("PUBLIC_SITE_URL","https://leehonghun.github.io/cheongma-law-portal/")
with sync_playwright() as p:
    browser=p.chromium.launch(headless=True)
    page=browser.new_page(viewport={"width":1440,"height":900},locale="ko-KR")
    errors=[]
    page.on("pageerror",lambda e: errors.append(str(e)))
    r=page.goto(URL,wait_until="domcontentloaded",timeout=30000)
    assert r and r.status==200, f"Public site HTTP status: {r.status if r else 'missing'}"
    assert "청마" in page.title(), page.title()
    assert page.locator("#radar-toggle").count()==1
    assert page.locator("#nav-count").inner_text().strip().isdigit()
    assert int(page.locator("#nav-count").inner_text())>=50
    assert page.locator("#dashboard-stats").is_visible()
    assert page.locator("#today-highlights").is_visible()
    assert page.locator('.logout-form').count()==0
    page.screenshot(path="live-portal.png",full_page=True)
    if page.locator("#latest-post-list").count()==0:
        from datetime import datetime, timedelta
        from zoneinfo import ZoneInfo
        today=datetime.now(ZoneInfo("Asia/Seoul")).date()
        for card in page.locator("#today-highlights .dash-highlight small").all_text_contents():
            posted=datetime.strptime(card.rsplit(" · ",1)[-1],"%Y.%m.%d").date()
            assert 0 <= (today-posted).days <= 30, card
        for row in page.locator("#work-updates tbody tr").all():
            assert int(row.locator("td").nth(1).inner_text().replace("건",""))>0
    page.locator("[data-tab='feed']").click()
    assert page.locator("#view-feed").is_visible()
    page.locator("#search").fill("녹색건축")
    assert page.locator("#post-rows tr").count()>0
    page.locator("[data-tab='coverage']").click()
    assert page.locator("#coverage-cards article").count()==36
    import json
    payload=json.loads(page.locator("#radar-data").text_content())
    assert payload["home_policy"]["mode"]=="recent_references"
    assert payload["publication_policy"]["mode"]=="forward_only"
    assert set(payload["new_publication_keys"]).issubset({r["key"] for r in payload["records"]})
    assert all(not r["key"].startswith("eims_") for r in payload["records"])
    assert all(s["id"]!="S07" for s in payload["sources"])
    assert len(payload.get("work_coverage",[]))==15, "Department work coverage missing"
    assert all(r.get("work_categories") for r in payload["records"]), "Unrelated public record"
    assert page.locator("#work-overview").count()==0
    page.locator("[data-tab='feed']").click()
    page.locator("[data-group='장수명']").click()
    assert page.locator("#view-feed").is_visible()
    assert not errors, "Browser JavaScript exceptions: "+"; ".join(errors)
    browser.close()
print("PASS: Public HTTP 200; navigation, source/period controls, data and original links.")
