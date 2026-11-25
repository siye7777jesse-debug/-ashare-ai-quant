"""Use public Sohu historical quote rows for stocks missing from the primary extension."""
import concurrent.futures as cf
import json, pathlib, threading, time
import requests

ROOT=pathlib.Path('sohu')
ROOT.mkdir(exist_ok=True)
target=set(json.loads(pathlib.Path('universe.json').read_text())['codes'])
old=pathlib.Path('extension')
missing=sorted(c for c in target if not (old/f'{c}.json').exists())
# We also audit a fixed small cross-provider sample selected by code ordering.
check=sorted(c for c in target if (old/f'{c}.json').exists())[::100]
jobs=sorted(set(missing)|set(check))
print('missing',len(missing),'crosschecks',len(check),'jobs',len(jobs),flush=True)
tls=threading.local()
stop=threading.Event()

def get(c):
    out=ROOT/f'{c}.json'
    if out.exists() or stop.is_set():return 'skipped'
    if not hasattr(tls,'s'):
        tls.s=requests.Session()
        tls.s.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://q.stock.sohu.com/'})
    url=f'https://q.stock.sohu.com/hisHq?code=cn_{c[2:]}&start=20260801&end=20261124&stat=1&order=D&period=d&rt=json'
    for attempt in range(2):
        if stop.is_set():return 'limited'
        try:
            r=tls.s.get(url,timeout=12)
            if r.status_code in (403,429):
                stop.set();return f'limited:{c}:{r.status_code}'
            r.raise_for_status()
            d=r.json()[0]
            assert d['status']==0
            rows=d['hq']
            assert rows and all(len(x)>=9 and len(x[0])==10 for x in rows)
            assert len({x[0] for x in rows})==len(rows)
            out.write_text(json.dumps(rows,separators=(',',':')))
            time.sleep(.15)
            return 'ok'
        except Exception as e:
            if attempt==1:return f'error:{c}:{type(e).__name__}:{str(e)[:80]}'
            time.sleep(.6)
if __name__=='__main__':
    errors=[]; ok=0; start=time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=8) as p:
        for i,f in enumerate(cf.as_completed([p.submit(get,c) for c in jobs]),1):
            t=f.result()
            if t in ('ok','skipped'):ok+=1
            else:errors.append(t)
            if i%100==0:print(i,ok,len(errors),round(time.monotonic()-start,1),flush=True)
    pathlib.Path('sohu-errors.json').write_text(json.dumps(errors,ensure_ascii=False))
    print('done',len(list(ROOT.glob('*.json'))),len(errors),'limited',stop.is_set(),flush=True)
