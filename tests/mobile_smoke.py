"""Exercise the mobile research entry points using only the checked-in snapshot."""
import json
from pathlib import Path
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def exercise(page):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route("https://**/*", lambda route: route.abort())
    page.goto(f"http://127.0.0.1:{server.server_port}/")
    page.wait_for_function("document.getElementById('directory-status').textContent.includes('已载入')")
    page.wait_for_function("!document.getElementById('report-symbol').disabled")

    page.locator("#stock-search").fill("茅台")
    page.locator("#stock-suggestions button").filter(has_text="600519").click()
    page.locator("#load").click()
    page.wait_for_function("Number(document.getElementById('count').textContent)>100")
    page.locator("#run").click()
    assert page.locator("#ret").inner_text() != "—", page.locator("#message").inner_text()
    page.locator("#oos-run").click()
    assert page.locator("#out-ret").inner_text() != "—"

    page.locator("#batch-search").fill("云南锗业 中科曙光")
    page.locator("#batch-add-code").click()
    chips = page.locator("#batch-selected button")
    assert chips.all_text_contents() == ["云南锗业 002428 ×", "中科曙光 603019 ×"]
    page.locator("#batch-search").fill("云南锗业、查无此股")
    page.locator("#batch-add-code").click()
    assert chips.count() == 2
    assert page.locator("#batch-search").input_value() == "查无此股"
    for name in ("云南锗业", "中科曙光"):
        chips.filter(has_text=name).click()

    for name in ["上海九百", "中际旭创"]:
        page.locator("#batch-search").fill(name)
        page.locator("#batch-suggestions button").first.click()
    page.locator("#batch-run").click()
    page.wait_for_function("document.getElementById('batch-summary').textContent.includes('成功 2/2')")
    page.locator("#batch-search").fill("000001")
    page.locator("#batch-add-code").click()
    assert page.locator("#batch-summary").inner_text() == ""
    page.locator("#batch-run").click()
    page.wait_for_function("document.getElementById('batch-summary').textContent.includes('成功 2/3')")
    assert "整组中位数暂缺" in page.locator("#batch-summary").inner_text()
    assert "000001" in page.locator("#batch-rows").text_content()
    page.locator("#report-symbol").select_option("300308")
    report = json.loads(Path("data/research.json").read_text())
    expected = next(item["windows"] for item in report["stocks"] if item["symbol"] == "300308")
    assert page.locator("#report-rows tr").count() == len(expected)
    latest = page.locator("#report-rows tr").first.inner_text()
    assert expected[-1]["end"] in latest
    assert ("年内截至" in latest) == expected[-1]["partial"]
    width = page.evaluate("document.documentElement.scrollWidth")
    if width > 390:
        outside = page.evaluate("""[...document.querySelectorAll('body *')].filter(
            el=>el.getBoundingClientRect().right>390 && el.getBoundingClientRect().width>0
        ).slice(0,15).map(el=>[el.tagName,el.id,el.className,el.getBoundingClientRect().right])""")
        raise AssertionError(f"390px viewport scrolls to {width}: {outside}")
    assert not errors, errors
    print("390x844 mobile Chromium: name search, single stock, holdout, two-stock charts and annual report passed.")


with ThreadingHTTPServer(("127.0.0.1", 0), QuietHandler) as server:
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844},
                                device_scale_factor=2, is_mobile=True, has_touch=True)
        exercise(page)
        browser.close()
    server.shutdown()
