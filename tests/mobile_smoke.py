import functools
import os
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright
class Quiet(SimpleHTTPRequestHandler):
 def log_message(self,*args): pass
root=os.getcwd()
server=ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Quiet,directory=root))
threading.Thread(target=server.serve_forever,daemon=True).start()
with sync_playwright() as p:
 browser=p.chromium.launch()
 page=browser.new_page(viewport={'width':390,'height':844},device_scale_factor=2,is_mobile=True,has_touch=True)
 errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.route('https://**/*',lambda route:route.abort())
 page.goto(f'http://127.0.0.1:{server.server_port}/')
 page.wait_for_function("document.getElementById('directory-status').textContent.includes('已载入')")
 page.locator('#stock-search').fill('茅台')
 page.locator('#stock-suggestions button').filter(has_text='600519').click()
 page.locator('#load').click()
 page.wait_for_function("Number(document.getElementById('count').textContent)>100")
 page.locator('#run').click()
 assert page.locator('#ret').inner_text()!='—',page.locator('#message').inner_text()
 page.locator('#oos-run').click()
 assert page.locator('#out-ret').inner_text()!='—'
 for name in ['上海九百','中际旭创']:
  page.locator('#batch-search').fill(name);page.locator('#batch-suggestions button').first.click()
 page.locator('#batch-run').click()
 page.wait_for_function("document.getElementById('batch-summary').textContent.includes('成功 2/2')")
 page.locator('#report-symbol').select_option('300308')
 assert page.locator('#report-rows tr').count()==8
 assert '年内截至' in page.locator('#report-rows tr').first.inner_text()
 assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
 assert not errors,errors
 print('390x844 mobile Chromium; external requests blocked:',page.locator('#directory-status').inner_text(),page.locator('#count').inner_text(),'bars;',page.locator('#batch-summary').inner_text().split('；')[0],'; 8 yearly windows; no overflow or page errors')
 browser.close()
server.shutdown()
