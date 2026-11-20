"""Exercise the mobile research entry points using only the checked-in snapshot."""
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

    for name in ["上海九百", "中际旭创"]:
        page.locator("#batch-search").fill(name)
        page.locator("#batch-suggestions button").first.click()
    page.locator("#batch-run").click()
    page.wait_for_function("document.getElementById('batch-summary').textContent.includes('成功 2/2')")
    page.locator("#report-symbol").select_option("300308")
    assert page.locator("#report-rows tr").count() == 8
    assert "年内截至" in page.locator("#report-rows tr").first.inner_text()
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
