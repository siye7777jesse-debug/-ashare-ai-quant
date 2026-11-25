import concurrent.futures as cf
import threading, pathlib, json, time
import requests

UNIVERSE=json.loads(pathlib.Path('universe.json').read_text())['codes']
ROOT=pathlib.Path('extension')
ROOT.mkdir(exist_ok=True)
tls=threading.local()
stop=threading.Event()
def get(code):
    out=ROOT/f'{code}.json'
    if out.exists(): return 'cached'
    if stop.is_set(): return f'not_requested:{code}'
    if not hasattr(tls,'session'):
        tls.session=requests.Session()
        tls.session.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://stockpage.10jqka.com.cn/'})
    res={}
    for mode in ('00','02'):
        url=f'https://d.10jqka.com.cn/v6/line/hs_{code[2:]}/{mode}/2026.js'
        for attempt in range(2):
            try:
                r=tls.session.get(url,timeout=10)
                if r.status_code in (429,403):
                    stop.set()
                    return f'limited:{code}:{r.status_code}'
                if r.status_code==404:
                    return f'404:{code}'
                r.raise_for_status()
                s=r.text
                data=json.loads(s[s.index('(')+1:s.rfind(')')])
                rows=[row.split(',')[:7] for row in data['data'].strip(';').split(';') if row]
                assert rows and all(len(x)==7 and len(x[0])==8 and x[0].isdigit() for x in rows)
                rows=[x for x in rows if x[0]<='20261124']
                assert len(set(x[0] for x in rows))==len(rows)
                res[mode]=rows
                break
            except Exception as exc:
                if attempt==1:return f'error:{code}:{mode}:{type(exc).__name__}:{str(exc)[:60]}'
                time.sleep(.5)
        time.sleep(.12)
    raw_dates=[r[0] for r in res['00']]
    adj_dates=[r[0] for r in res['02']]
    if raw_dates!=adj_dates:return f'date-mismatch:{code}'
    out.write_text(json.dumps(res,separators=(',',':')))
    return 'ok'
if __name__=='__main__':
    errors=[]; ok=0
    start=time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=10) as pool:
        for i,f in enumerate(cf.as_completed([pool.submit(get,code) for code in UNIVERSE]),1):
            t=f.result()
            if t=='ok' or t=='cached':ok+=1
            else: errors.append(t)
            if i%100==0:print(i,ok,len(errors),round(time.monotonic()-start,1),flush=True)
    pathlib.Path('fetch-errors.json').write_text(json.dumps(errors,ensure_ascii=False))
    print('finished',len(list(ROOT.glob('*.json'))),len(errors),'stopped',stop.is_set(),flush=True)
