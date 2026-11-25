import duckdb, pathlib, json, numpy as np, pandas as pd

def affine_compatible(xs,ys,eps):
    lower=0.; upper=float('inf')
    for i in range(len(xs)):
        for j in range(i):
            dx=xs[i]-xs[j];dy=ys[i]-ys[j]
            if abs(dx)<1e-9:
                if abs(dy)>2*eps+1e-8:return False
                continue
            if dx<0:dx=-dx;dy=-dy
            lower=max(lower,(dy-2*eps)/dx)
            upper=min(upper,(dy+2*eps)/dx)
            if lower>upper+1e-8:return False
    return upper>0
def inspect(src,raw,adj):
    prev_raw=None;prev_adj=None
    rows=[]
    for a,b in zip(raw,adj):
        if src=='qq':
            x=list(map(float,[a[1],a[3],a[4],a[2]])); y=list(map(float,[b[1],b[3],b[4],b[2]]))
            day=a[0]; eps=.0006
        else:
            x=list(map(float,a[1:5]));y=list(map(float,b[1:5]))
            day=a[0][:4]+'-'+a[0][4:6]+'-'+a[0][6:];eps=.0051
        if min(x+y)<=0:continue
        if prev_raw is not None and day>='2026-09-01':
            same=affine_compatible(x+[prev_raw],y+[prev_adj],eps)
            if max(x)>min(x):
                k=(max(y)-min(y))/(max(x)-min(x))
                est=round((prev_adj-np.median(np.array(y)-k*np.array(x)))/k,2) if k>0 else np.nan
            else:est=np.nan
            rows.append((day,prev_raw,same,est))
        prev_raw=x[-1];prev_adj=y[-1]
    return rows
r=[]
for source,dirname in [('ths','extension'),('qq','qq')]:
    for f in pathlib.Path(dirname).glob('*.json'):
        d=json.loads(f.read_text())
        keys=('00','02') if source=='ths' else ('raw','hfq')
        code=f.stem[:2]+'.'+f.stem[2:]
        try:
            r.extend((source,code,*a) for a in inspect(source,d[keys[0]],d[keys[1]]))
        except Exception:pass
df=pd.DataFrame(r,columns=['source','code','date','prev_raw','same','est'])
df.date=pd.to_datetime(df.date)
con=duckdb.connect('archive.duckdb',read_only=True)
con.register('r',df)
print(con.execute("""
select source,count(*),avg((abs(prev_raw-h.ref)<.00001)::int),
   sum((not same)::int) suspicious,
   sum((not same and abs(prev_raw-h.ref)<.00001)::int) false_positive,
   sum((same and abs(prev_raw-h.ref)>=.00001)::int) false_negative,
   sum((not same and abs(est-h.ref)<.00001)::int) est_correct_suspicious
from r join hist h using(date,code)
where h.trading and h.amount>0 and not h.risk group by source
""").fetchall())
sus=df[(df.date>'2026-09-24')&~df.same]
print('suspected extension',sus.groupby('source').size().to_dict(),'stocks',sus.code.nunique())
print(sus.head(30).to_string(index=False))
sus.to_json('suspected.json',orient='records',date_format='iso')
