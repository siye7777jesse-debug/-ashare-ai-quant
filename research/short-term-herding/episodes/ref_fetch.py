import json,pathlib,datetime as dt,concurrent.futures as cf,threading,time
import requests

jobs=[];done={}
sus=json.load(open('suspected.json'))
for s in sus:
    c=s['code'].replace('.','');d=s['date'][:10]
    f=pathlib.Path('sohu')/(c+'.json')
    known=next((x for x in json.loads(f.read_text()) if x[0]==d),None) if f.exists() else None
    if known:done[c+'|'+d]=known
    else:jobs.append((c,d))
stop=threading.Event();tls=threading.local()
print('reference observations',len(sus),'known',len(done),'to fetch',len(jobs),flush=True)
def fetch(job):
    c,d=job
    if stop.is_set():return None
    if not hasattr(tls,'s'):
        tls.s=requests.Session();tls.s.headers.update({'User-Agent':'Mozilla/5.0','Referer':'https://q.stock.sohu.com/'})
    date=dt.date.fromisoformat(d)
    start=(date-dt.timedelta(days=4)).strftime('%Y%m%d')
    end=min(date+dt.timedelta(days=4),dt.date(2026,11,24)).strftime('%Y%m%d')
    url=f'https://q.stock.sohu.com/hisHq?code=cn_{c[2:]}&start={start}&end={end}&stat=1&order=D&period=d&rt=json'
    try:
        r=tls.s.get(url,timeout=9)
        if r.status_code in (403,429):
            stop.set();return None
        if not r.ok:return None
        rows=r.json()[0]['hq']
        row=next(x for x in rows if x[0]==d)
        time.sleep(.15)
        return (c+'|'+d,row)
    except Exception:return None
with cf.ThreadPoolExecutor(max_workers=6) as p:
    for i,v in enumerate(p.map(fetch,jobs),1):
        if v:done[v[0]]=v[1]
        if i%50==0:print(i,len(done),flush=True)
pathlib.Path('sohu-references.json').write_text(json.dumps(done,separators=(',',':')))
print('done',len(done),'of',len(sus),'limited',stop.is_set(),flush=True)
