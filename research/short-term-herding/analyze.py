"""Chronological event study for the fixed specification in protocol.md."""
import json
from pathlib import Path
import warnings

import duckdb
import numpy as np
import pandas as pd

from prepare import events, prepare

END = '2026-06-30'
SEGMENTS = {
    '2019–2021': ('2019-01-01','2021-12-31'),
    '2022–2023': ('2022-01-01','2023-12-31'),
    '2024–2026H1': ('2024-01-01', END),
}
VARIANTS = {'主规则': (1.30,3), '集中1.15': (1.15,3), '集中1.50': (1.50,3),
            '入榜2日':(1.30,2), '入榜4日':(1.30,4)}

def attach_emotion(con, event):
    emotion = con.execute("""
      select t.seq,avg(t.ret) as prior_limit_return,count(*) as emotion_sample
      from series t join series prev on t.code=prev.code and t.seq=prev.seq+1
      where prev.eligible and prev.limit_close and t.eligible group by t.seq
    """).df()
    return event.merge(emotion,on='seq',how='left')

def label(con, event, start, end):
    cal = con.sql("select * from cal order by seq").df()
    last = int(cal.loc[cal.date.le(end),'seq'].max())
    eligible = event.loc[event.date.ge(start) & event.seq.le(last-10)].copy().reset_index(drop=True)
    eligible['event_id'] = eligible.index
    con.register('eligible_events',eligible)
    paths = con.execute("""
        select e.event_id, g.h as day_offset, p.traded, p.isST, p.open, p.amount,
               p.adj_open, p.adj_close, p.limit_open_up, p.limit_open_down, c.date as bar_date
        from eligible_events e cross join range(1,11) g(h)
        join cal c on c.seq=e.seq+g.h
        left join series p on p.code=e.code and p.seq=c.seq
        order by e.event_id,day_offset
    """).df()
    con.unregister('eligible_events')
    assert len(paths)==10*len(eligible)
    if eligible.empty: return eligible, paths
    peaks = paths[paths.day_offset.le(3)].groupby('event_id').adj_close.max()
    eligible['repair']=(peaks.ge(eligible.pre_dip)|np.isclose(peaks,eligible.pre_dip,rtol=1e-10,atol=0)).astype(int)
    eligible['repair_days'] = paths[paths.day_offset.le(3)].groupby('event_id').adj_close.count()
    return eligible,paths

def simulate(events, paths, slip):
    budget=10000.
    assert np.array_equal(paths.event_id.to_numpy(),np.repeat(events.event_id.to_numpy(),10))
    by_event=lambda name: paths[name].to_numpy().reshape(-1,10)
    open_price=by_event('open')[:,0]
    enter=paths.traded.eq(True).to_numpy(dtype=bool,na_value=False).reshape(-1,10)[:,0]
    enter &= paths.limit_open_up.eq(False).to_numpy(dtype=bool,na_value=False).reshape(-1,10)[:,0]
    enter &= by_event('isST')[:,0]=='0'
    safe_price=np.where(enter,open_price,1)
    cash_limit=min(budget/(1+slip+.0003),(budget-5)/(1+slip))
    cash_lot=np.floor(cash_limit/(100*safe_price))
    volume_lot=np.floor((events.liquidity.to_numpy()*.001)/(100*safe_price))
    qty=np.where(enter,np.minimum(cash_lot,volume_lot)*100,0)
    filled=enter & (qty>0)
    reason=np.full(len(events),'entry_block',dtype=object)
    reason[enter & (cash_lot<1)]='cash'
    reason[enter & (cash_lot>=1) & (volume_lot<1)]='liquidity'

    possible=(paths.traded.eq(True)&paths.limit_open_down.eq(False)).to_numpy(dtype=bool,na_value=False).reshape(-1,10)
    possible[:,:3]=False
    exit_found=possible.any(axis=1)
    ex=possible.argmax(axis=1)
    size_in=np.where(filled,safe_price*qty,0)
    completed=filled & exit_found
    unresolved=filled & ~exit_found
    rr=np.arange(len(events))
    adj=by_event('adj_open')
    size_out=np.divide(adj[rr,ex],adj[:,0],out=np.zeros(len(events)),where=completed)*size_in
    fee_in=np.where(filled,np.maximum(5,size_in*.0003)+slip*size_in,0)
    tax=np.where(by_event('bar_date')[rr,ex]<np.datetime64('2023-08-28'),.001,.0005)
    fee_out=np.where(completed,np.maximum(5,size_out*.0003)+(tax+slip)*size_out,0)
    gross=np.where(unresolved,np.nan,(size_out-size_in)/budget)
    net=(size_out-size_in-fee_in-fee_out)/budget
    reason[completed & (ex==3)]='sold'
    reason[completed & (ex>3)]='delayed'
    reason[unresolved]='unresolved'
    return pd.DataFrame(dict(execution=reason,net=net,gross=gross,exposure=size_in/budget,
                             exit_offset=np.where(completed,ex+1,np.nan)),index=events.index)

def diffs(events,key):
    g=events.groupby(['date','lead_industry'])[key].mean().unstack()
    g=g.reindex(columns=[True,False]).dropna()
    return (g[True]-g[False]).rename('gap')

def interval(deltas, cal, block=20):
    data=deltas.reindex(cal).to_numpy()
    n=len(data)
    anchors=np.random.default_rng(224608).integers(0,n,(3000,(n+block-1)//block))
    pos=((anchors[...,None]+np.arange(block))%n).reshape(3000,-1)[:,:n]
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',RuntimeWarning)
        boot=np.nanmean(data[pos],axis=1)
    return np.nanquantile(boot,[.025,.975]).tolist()

def measure(events, dates):
    rows={}
    paired=events[events.date.isin(diffs(events,'repair').index)]
    for key,value in [('抱团领先行业',True),('同日对照',False)]:
        e=paired[paired.lead_industry.eq(value)]
        rows[key]=dict(events=len(e),repair=float(e.groupby('date').repair.mean().mean()),
                       no_full_price_path=int(e.repair_days.lt(3).sum()))
    d=diffs(events,'repair')
    return dict(days=len(d),gap=float(d.mean()),ci=interval(d,dates),groups=rows)

def concentration_rank_ic(events, paths, dates):
    opens = paths[paths.day_offset.isin([1,4])].pivot(index='event_id',columns='day_offset',values='adj_open')
    sample = events.assign(forward_return=opens[4]/opens[1]-1).dropna(subset=['forward_return'])
    counts = sample.groupby('date').size()
    sample = sample[sample.date.isin(counts[counts.ge(5)].index)].copy()
    ranks = sample.groupby('date')[['concentration','forward_return']].rank()
    changes = ranks.sub(ranks.groupby(sample.date).transform('mean'))
    product = changes.concentration * changes.forward_return
    squares = changes.pow(2).groupby(sample.date).sum()
    ic = (product.groupby(sample.date).sum() / np.sqrt(squares.prod(axis=1))).dropna()
    return dict(days=len(ic), events=int(counts.reindex(ic.index).sum()),
                mean=float(ic.mean()), ci=interval(ic,dates))

def execution_table(events,paths,dates,slip):
    outcome=simulate(events,paths,slip)
    e=events.join(outcome)
    paired=e[e.date.isin(diffs(e,'net').index)]
    g=paired.groupby('lead_industry').agg(
        net=('net','mean'),gross=('gross','mean'),exposure=('exposure','mean'),
        count=('net','size'))
    result={str(k):{**v,'status':paired.loc[paired.lead_industry.eq(k),'execution'].value_counts().to_dict()} for k,v in g.to_dict('index').items()}
    gap=diffs(e,'net')
    return dict(groups=result,same_date_delta=float(gap.mean()),ci=interval(gap,dates)),outcome

def assert_prefix(event, bound):
    truncated=duckdb.connect('prefix-'+bound+'-v2.duckdb')
    if 'research' not in {row[0] for row in truncated.execute('show tables').fetchall()}:
        prepare(truncated,bound,persistent=True)
    old=attach_emotion(truncated,events(truncated,*VARIANTS['主规则']))
    cols=['date','code','industry','lead_industry','prior_momentum','concentration','dip','prior_limit_return']
    pd.testing.assert_frame_equal(event.loc[event.date.le(bound),cols].reset_index(drop=True),
                                  old[cols],check_exact=False,rtol=1e-8,atol=1e-10)
    truncated.close()
    return len(old)

def audit(con):
    assert con.execute("select count(*) from membership group by snapshot,code having count(*)>1 limit 1").fetchall()==[]
    assert con.execute("select count(*) from base group by date,code having count(*)>1 limit 1").fetchall()==[]
    assert con.execute("select count(*) from research where snapshot>=date").fetchall()==[(0,)]
    return con.sql("""select count(*) as rows, count(distinct code) as stocks,
       count(distinct industry) as industries, min(date) as first_date, max(date) as last_date
       from research where date>='2019-01-01'""").df().iloc[0].to_dict()

def main():
    con=duckdb.connect('computed-'+END+'-v2.duckdb')
    if 'research' not in {row[0] for row in con.execute('show tables').fetchall()}:
        prepare(con, END, persistent=True)
    else:
        con.execute("SET threads=4")
        con.execute("SET memory_limit='3GB'")
    print('prepared',flush=True)
    stats={'data':audit(con),'periods':{},'robust':{},'prefix':{}}
    cal=con.sql('select date from cal order by date').df().date
    base=attach_emotion(con,events(con,*VARIANTS['主规则']))
    print('signals',len(base),flush=True)
    all_events=[]
    for name,(start,end) in SEGMENTS.items():
        label_rows,paths=label(con,base,start,end)
        dates=cal[cal.between(start,end)]
        if len(paths): assert paths.bar_date.max()<=pd.Timestamp(end)
        section=measure(label_rows,dates)
        section['total_signals']=label_rows.lead_industry.value_counts().rename(index={True:'抱团领先行业',False:'对照'}).to_dict()
        section['execution']={}
        for bps in (10,30,60):
            section['execution'][bps],out=execution_table(label_rows,paths,dates,bps/10000)
            if bps==10: all_events.append(label_rows.join(out))
        stats['periods'][name]=section
        print(name,section['days'],section['gap'],flush=True)

    for name,rule in VARIANTS.items():
        e,p=label(con,events(con,*rule),'2024-01-01', END)
        stats['robust'][name]=measure(e,cal[cal.between('2024-01-01',END)])
    for year in (2024,2025,2026):
        e,_=label(con,base,f'{year}-01-01',min(f'{year}-12-31',END))
        stats['robust'][str(year)]=measure(e,cal[cal.dt.year.eq(year)])
    for key,condition in [('昨日涨停股当日平均收益为正',base.prior_limit_return.gt(0)),
                          ('昨日涨停股当日平均收益非正',base.prior_limit_return.le(0))]:
        e,_=label(con,base[condition & base.emotion_sample.ge(10)],'2024-01-01',END)
        stats['robust'][key]=measure(e,cal[cal.between('2024-01-01',END)])
    # A second comparison holds the industry condition fixed and tests the extra value of concentration.
    industry = events(con,0,3)
    industry = industry[industry.lead_industry].copy()
    industry['lead_industry'] = industry.concentration.ge(1.30)
    z,p=label(con,industry,'2024-01-01',END)
    holdout_dates = cal[cal.between('2024-01-01',END)]
    stats['concentration_increment']=measure(z,holdout_dates)
    stats['concentration_rank_ic']=concentration_rank_ic(z,p,holdout_dates)
    for bound in ('2021-12-31','2023-12-31'):
        stats['prefix'][bound]=assert_prefix(base,bound)
        print('prefix verified',bound,flush=True)
    Path('results.json').write_text(json.dumps(stats,default=str,ensure_ascii=False,indent=2,allow_nan=False))
    pd.concat(all_events,ignore_index=True).to_json('event-results.jsonl.gz',orient='records',lines=True,compression='gzip',force_ascii=False,date_format='iso')

if __name__=='__main__':main()
