"""Historical board-wide resonance cycles with rotating leaders."""
import argparse
from pathlib import Path
import json, math
import numpy as np
import pandas as pd
import duckdb

LABELS={'C27':'医药制造（创新药代理）','F52':'零售','media':'出版影视文化（传媒代理）',
        'equipment':'通用/专用设备（机器人代理）','yang':'洋字辈'}
GROUPS=list(LABELS)
START='2026-07-01'
END='2026-11-24'

SQL="""
create or replace temp table known_membership as
select cast(snapshot_date as date) snapshot, code, code_name, industry, left(industry,3) sector
from read_parquet('raw/industry_snapshots/*.parquet')
where snapshot_date>='2025-11-01' and try_cast(updateDate as date)<=cast(snapshot_date as date)
and code_name is not null;
create or replace temp table calendar_membership as
select c.date,c.seq,m.snapshot
from cal c asof left join (select distinct snapshot from known_membership) m on c.date>m.snapshot;
create or replace temp table market_daily as
select date,seq,count(*) members,avg(ret) market_ret,sum(amount_lo) amount_lo,sum(amount_hi) amount_hi,
       sum(board::int) boards
from quote where date<=? group by date,seq;
create or replace temp table market_window as
select *,sum(ln(1+market_ret)) over five market_log5,count(*) over five market_n5
from market_daily
window five as (order by seq range between 4 preceding and current row);
create or replace temp table stock_window as
with s as (
 select q.*,sum(logret) over five stock_log5,count(*) over five stock_n5
 from quote q where date<=?
 window five as (partition by code order by seq range between 4 preceding and current row)
)
select s.*,m.market_log5,m.market_n5,md.snapshot,k.code_name,k.industry,k.sector,
       coalesce(st.height,0) height,
       (stock_n5=5 and market_n5=5 and round(stock_log5-market_log5,10)>0) outperforms
from s join market_window m using(seq)
join calendar_membership md on md.date=s.date
join known_membership k on k.snapshot=md.snapshot and k.code=s.code
left join streaks st on st.code=s.code and st.seq=s.seq;

create or replace temp table members as
select *, 'industry:'||sector cohort from stock_window where sector is not null and sector<>''
union all select *, 'C27' cohort from stock_window where sector='C27'
union all select *, 'F52' cohort from stock_window where sector='F52'
union all select *, 'media' cohort from stock_window where sector in ('R86','R87','R88')
union all select *, 'equipment' cohort from stock_window where sector in ('C34','C35')
union all select *, 'yang' cohort from stock_window where code_name like '%洋%';

create or replace temp table group_daily as
with g as (
 select cohort,date,seq,count(*) members,count(*) filter(where stock_n5=5 and market_n5=5) n5,
        avg(ret) board_ret,
        avg((outperforms)::int) filter(where stock_n5=5 and market_n5=5) breadth5,
        sum(amount_lo) group_lo,sum(amount_hi) group_hi,
        sum(board::int) boards,max(height) max_height
 from members group by cohort,date,seq
)
select g.*,m.market_ret,m.market_log5,
       g.group_lo/m.amount_hi share_lo,g.group_hi/m.amount_lo share_hi,
       round(avg(abs(g.board_ret)) over(partition by cohort order by seq range between 4 preceding and current row),10) abs_ret5
from g join market_window m using(seq)
where g.members>=10 and g.n5>=ceil(g.members*.8);

create or replace temp table panel as
with f as (
 select *,sum(ln(1+board_ret)) over five group_log5,count(*) over five seen5,
        count(*) over prior seen20,
        avg(share_lo) over five recent_lo,avg(share_hi) over five recent_hi,
        avg(share_lo) over prior prior_lo,avg(share_hi) over prior prior_hi
 from group_daily
 window five as (partition by cohort order by seq range between 4 preceding and current row),
 prior as (partition by cohort order by seq range between 24 preceding and 5 preceding)
)
select *,round(exp(group_log5)-1,10) group_r5,
       round(exp(group_log5-market_log5)-1,10) relative5,
       round(recent_lo/nullif(prior_hi,0),10) concentration_lo,
       round(recent_hi/nullif(prior_lo,0),10) concentration_hi
from f where seen5=5 and seen20>=17;
"""

def build(con, end):
    # DuckDB can execute the statements one at a time using placeholders.
    for stmt in SQL.split(';'):
        stmt=stmt.strip()
        if stmt:
            con.execute(stmt,[end] if '?' in stmt else [])

def conditions(row, breadth=.55, multiple=1.15):
    if row is None:return None
    values=(row.relative5,row.breadth5,row.concentration_lo,row.concentration_hi)
    if not all(np.isfinite(v) for v in values):return None
    positive=row.relative5>=.02 and row.breadth5>=breadth and row.concentration_lo>=multiple
    retreat=sum((row.relative5<=0,row.breadth5<.45,row.concentration_hi<1.05))>=2
    return positive,retreat

def episodes(panel, cal, breadth=.55, multiple=1.15, exit_days=3):
    byseq={int(row.seq):row for row in panel.itertuples(index=False)}
    out=[]; current=None; leads=0; fails=0
    for day in cal.itertuples(index=False):
        seq=int(day.seq)
        if day.date<pd.Timestamp('2026-05-01'):continue
        row=byseq.get(seq)
        state=conditions(row,breadth,multiple)
        if state is None:
            leads=fails=0
            if current is not None:current['missing_days']+=1
            continue
        positive,retreat=state
        if current is None:
            leads=leads+1 if positive else 0
            if leads>=2:
                current={'start':seq,'end':None,'start_date':day.date,'end_date':None,
                         'start_relative5':row.relative5,'start_breadth5':row.breadth5,
                         'start_concentration_lo':row.concentration_lo,
                         'start_concentration_hi':row.concentration_hi,
                         'members':int(row.members),'missing_days':0,
                         'first_warning':None,'positive_days':1,'max_relative5':row.relative5}
                fails=0;leads=0
            continue
        if positive:current['positive_days']+=1
        current['max_relative5']=max(current['max_relative5'],row.relative5)
        if retreat:
            if fails==0:current['first_warning']=day.date
            fails+=1
        else:
            fails=0;current['first_warning']=None
        if fails>=exit_days:
            current['end']=seq;current['end_date']=day.date
            current['duration']=seq-current['start']
            out.append(current);current=None;fails=leads=0
    if current is not None:
        current['duration']=int(cal.seq.max())-current['start']+1
        out.append(current)
    return out

def clip(items):
    return [e for e in items if e['end_date'] is None or e['end_date']>=pd.Timestamp(START)]

def main(db,out,end=END, prefix=None):
    with duckdb.connect(db,read_only=True) as con:
        build(con,end)
        cal=con.sql("select date,seq from cal order by seq").df()
        cal=cal[cal.date.le(end)]
        panel=con.sql("select * from panel order by cohort,seq").df()
        assert con.execute("select count(*) from stock_window where snapshot>=date").fetchall()==[(0,)]
        duplicates=con.execute("select count(*) from (select snapshot,code,count(*) n from known_membership group by snapshot,code having count(*)>1)").fetchall()[0][0]
        assert duplicates==0
        users=panel[panel.cohort.isin(GROUPS)]
        if prefix:
            users.to_pickle(prefix)
        bytheme={}
        settings={'main':(.55,1.15,3),'breadth_50':(.5,1.15,3),'breadth_60':(.6,1.15,3),
                  'concentration_105':(.55,1.05,3),'concentration_125':(.55,1.25,3),
                  'exit_2':(.55,1.15,2),'exit_5':(.55,1.15,5)}
        all_episodes={}
        for key,group in panel.groupby('cohort',sort=True):
            base=clip(episodes(group,cal))
            for episode in base:episode["cohort"]=key
            all_episodes[key]=base
            if key not in GROUPS:continue
            for e in base:
                leaders=con.execute("""select code,code_name,round(exp(stock_log5)-1,10),height
                   from members where cohort=? and seq=? and stock_n5=5
                   order by stock_log5 desc,code limit 5""",[key,e['start']]).fetchall()
                e['leaders']=[dict(code=c,name=n,r5=r,height=h) for c,n,r,h in leaders]
            metrics={}
            for m,g in group.loc[group.date.ge(START)].groupby(group.date.dt.to_period('M')):
                rel=(1+g.board_ret).prod()/(1+g.market_ret).prod()-1
                mask=(g.relative5>=.02)&(g.breadth5>=.55)&(g.concentration_lo>=1.15)
                metrics[str(m)]=dict(observed=len(g),relative=round(rel,10),resonance_days=int(mask.sum()),
                      mean_breadth=float(g.breadth5.mean()),mean_members=float(g.members.mean()))
            variants={}
            for variant,(b,m,x) in settings.items():
                es=clip(episodes(group,cal,b,m,x))
                variants[variant]=[dict(start=e['start_date'],end=e['end_date'],duration=e['duration']) for e in es]
            raw=group.loc[group.date.ge(START),['date','relative5','group_r5','breadth5','members','n5',
               'concentration_lo','concentration_hi','boards','max_height']].to_dict('records')
            bytheme[key]=dict(label=LABELS[key],episodes=base,months=metrics,variants=variants,daily=raw)
        # Actual sector-wide episode distribution, excluding the overlapping user-provided baskets.
        industry_episodes=[e for key,es in all_episodes.items() if key.startswith('industry:') for e in es]
        industry_closed=[e for e in industry_episodes if e['end_date'] is not None and e['start_date']>=pd.Timestamp(START)]
        counts=[e['duration'] for e in industry_closed]
        distribution=dict(complete=len(counts),median=float(np.median(counts)),p25=float(np.quantile(counts,.25)),
                          p75=float(np.quantile(counts,.75)),max=int(max(counts))) if counts else {}
        result=dict(start=START,end=end,groups=bytheme,industry_distribution=distribution,
                    actual_industry_count=sum(k.startswith('industry:') for k in all_episodes),
                    industry_closed=industry_closed)
        Path(out).write_text(json.dumps(result,ensure_ascii=False,indent=2,default=encode,allow_nan=False))
        return result

def encode(x):
    if isinstance(x,pd.Timestamp):return str(x.date())
    if isinstance(x,np.integer):return int(x)
    if isinstance(x,np.floating):return float(x)
    raise TypeError(type(x))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('db');p.add_argument('out');p.add_argument('--end',default=END);p.add_argument('--prefix')
    a=p.parse_args()
    r=main(a.db,a.out,a.end,a.prefix)
    for name,g in r['groups'].items():
        print(name,g['label'],[(str(e['start_date'])[:10],str(e['end_date'])[:10],e['duration']) for e in g['episodes']],flush=True)
    print('industry',r['actual_industry_count'],r['industry_distribution'])
