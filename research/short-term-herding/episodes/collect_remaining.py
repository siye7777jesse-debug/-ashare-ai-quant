"""Recover unavailable exact amount rows; preserve actual price and volume fallback."""
import concurrent.futures as cf
import json,pathlib,threading,time
import requests

SOHU=pathlib.Path('sohu')
QQ=pathlib.Path('qq');QQ.mkdir(exist_ok=True)
THS=pathlib.Path('extension')
target=set(json.loads(pathlib.Path('universe.json').read_text())['codes'])
tls=threading.local()
sohu_stop=threading.Event()
qq_stop=threading.Event()

def session():
    if not hasattr(tls,'s'):
        tls.s=requests.Session()
        tls.s.headers.update({'User-Agent':'Mozilla/5.0'})
    return tls.s

def get_sohu(c):
    if sohu_stop.is_set():return False
    url=f'https://q.stock.sohu.com/hisHq?code=cn_{c[2:]}&start=20260901&end=20261124&stat=1&order=D&period=d&callback=historySearchHandler&rt=jsonp'
    try:
        r=session().get(url,timeout=12)
        if r.status_code in (403,429):sohu_stop.set();return False
        if not r.ok:return False
        t=r.text
        d=json.loads(t[t.index('(')+1:t.rfind(')')])[0]
        if d['status']!=0:return False
        rows=d['hq']
        if not rows or any(len(x)<9 for x in rows):return False
        (SOHU/f'{c}.json').write_text(json.dumps(rows,separators=(',',':')))
        return True
    except Exception:return False

def get_qq(c):
    if qq_stop.is_set():return False
    out={}
    for adjust in ('','hfq'):
        if qq_stop.is_set():return False
        url=f'https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={c},day,2026-08-01,2026-11-24,120,{adjust}'
        try:
            r=session().get(url,timeout=12)
            if r.status_code in (403,429):qq_stop.set();return False
            if not r.ok:return False
            d=r.json()['data'][c]
            rows=d.get(adjust+'day') or d.get('day')
            rows=[row[:6] for row in rows if row[0]<='2026-11-24']
            if not rows:return False
            out[adjust or 'raw']=rows
        except Exception:return False
        time.sleep(.1)
    if [x[0] for x in out['raw']]!=[x[0] for x in out['hfq']]:return False
    (QQ/f'{c}.json').write_text(json.dumps(out,separators=(',',':')))
    return True

def get(c):
    if (SOHU/f'{c}.json').exists() or (THS/f'{c}.json').exists():return 'cached'
    if get_sohu(c):return 'sohu'
    if get_qq(c):return 'qq'
    return f'failed:{c}'

if __name__=='__main__':
    previous=json.load(open('sohu-errors.json'))
    if any(x.startswith('limited:') for x in previous):sohu_stop.set()
    jobs=[c for c in sorted(target) if not (SOHU/f'{c}.json').exists() and not (THS/f'{c}.json').exists()]
    print('remaining',len(jobs),'sohu limited earlier',sohu_stop.is_set(),flush=True)
    status=[]
    start=time.monotonic()
    with cf.ThreadPoolExecutor(max_workers=8) as p:
        for i,t in enumerate(p.map(get,jobs),1):
            status.append(t)
            if i%50==0:print(i,sum(s=='sohu' for s in status),sum(s=='qq' for s in status),sum(s.startswith('failed') for s in status),round(time.monotonic()-start,1),flush=True)
    pathlib.Path('remaining-status.json').write_text(json.dumps(status))
    print('done',len(status),'sohu limited',sohu_stop.is_set(),'qq limited',qq_stop.is_set(),flush=True)
