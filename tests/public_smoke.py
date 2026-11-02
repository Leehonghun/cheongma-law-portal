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
    assert int(page.locator("#nav-count").inner_text())>=500
    assert page.locator("#home-period").input_value()=="365"
    assert page.locator("#home-source").input_value()=="all"
    assert page.locator("#latest-post-list .today-card").count()>0
    assert page.locator("#latest-post-list .today-link").count()==0
    assert page.locator('.logout-form').count()==0, "Legacy login must be removed"
    initial=page.locator("#latest-post-list .today-card").count()
    page.screenshot(path="live-portal.png",full_page=True)
    page.locator("#home-source").select_option("중앙부처")
    assert page.locator("#latest-post-list .today-card").count()>0
    page.locator("#home-source").select_option("지자체")
    assert "개별 고시·공고 원문" in page.locator("#latest-post-list").inner_text()
    page.locator("#home-source").select_option("all")
    page.locator("#home-period").select_option("all")
    assert page.locator("#latest-post-list .today-card").count()>=initial
    page.locator("[data-tab='feed']").click()
    assert page.locator("#view-feed").is_visible()
    page.locator("#search").fill("녹색건축")
    assert page.locator("#post-rows tr").count()>0
    page.locator("[data-tab='coverage']").click()
    assert page.locator("#coverage-cards article").count()==37
    assert not errors, "Browser JavaScript exceptions: "+"; ".join(errors)
    browser.close()
print("PASS: Public HTTP 200; navigation, source/period controls, data and original links.")
