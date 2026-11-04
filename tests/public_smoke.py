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
    assert int(page.locator("#nav-count").inner_text())>=300
    assert page.locator("#home-period").input_value()=="365"
    assert page.locator("#home-source").input_value()=="all"
    assert page.locator("#home-kind").input_value()=="all"
    assert page.locator("#latest-post-list .today-card").count()>0
    assert page.locator("#latest-post-list .today-link").count()==0
    assert page.locator('.logout-form').count()==0, "Legacy login must be removed"
    initial=page.locator("#latest-post-list .today-card").count()
    page.screenshot(path="live-portal.png",full_page=True)
    page.locator("#home-source").select_option("중앙부처")
    assert page.locator("#latest-post-list .today-card").count()>0
    page.locator("#home-source").select_option("지자체")
    city_text=page.locator("#latest-post-list").inner_text()
    assert "세종시 녹색건축물 설계기준 안내 책자" in city_text, city_text[:300]
    page.locator("#home-kind").select_option("해설·매뉴얼")
    assert "세종시 녹색건축물 설계기준 안내 책자" in page.locator("#latest-post-list").inner_text()
    page.locator("#home-kind").select_option("all")
    page.locator("#home-source").select_option("all")
    page.locator("#home-period").select_option("all")
    assert page.locator("#latest-post-list .today-card").count()>=initial
    expand=page.locator("#latest-post-list button.soft-button")
    assert expand.count()>0, "Relevant candidates must remain expandable, not silently hidden"
    expand.first.click()
    assert page.locator("#latest-post-list .today-card").count()>initial
    page.locator("#home-source").select_option("지자체")
    page.locator("#home-kind").select_option("기준·고시")
    assert "환경영향평가" not in page.locator("#latest-post-list").inner_text()
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
    assert not errors, "Browser JavaScript exceptions: "+"; ".join(errors)
    browser.close()
print("PASS: Public HTTP 200; navigation, source/period controls, data and original links.")
