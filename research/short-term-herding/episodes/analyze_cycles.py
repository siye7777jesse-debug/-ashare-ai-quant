"""Daily reconstruction of the previously specified cross-industry core cohorts."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

import duckdb
import numpy as np
import pandas as pd
import requests

START='2026-07-01'
ARCHIVE_END='2026-09-24'
END='2026-11-24'
HERE=Path(__file__).resolve().parent
CODE_RE=r'^(sh\.60[0135][0-9]{3}|sz\.00[0123][0-9]{3})$'

def tick(x):
    return float(Decimal(str(x)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP))

def slope_bounds(xs, ys, eps):
    """Feasible positive slopes of an affine quote mapping with rounded prices."""
    low,high=0.,float('inf')
    for i in range(len(xs)):
        for j in range(i):
            dx,dy=xs[i]-xs[j],ys[i]-ys[j]
            if abs(dx)<1e-9:
                if abs(dy)>2*eps+1e-8:return None
                continue
            if dx<0:dx,dy=-dx,-dy
            low=max(low,(dy-2*eps)/dx)
            high=min(high,(dy+2*eps)/dx)
            if low>high+1e-8:return None
    return (low,high) if high>0 else None

def confirmed_reference(xs,ys,previous_raw,previous_adj,eps):
    if previous_raw is None:return np.nan,'no_previous_quote'
    if slope_bounds(xs+[previous_raw],ys+[previous_adj],eps) is not None:
        return previous_raw,'prior_raw_close'
    feasible=slope_bounds(xs,ys,eps)
    if not feasible:return np.nan,'uncertain'
    lower,upper=feasible
    if lower<=0 or not np.isfinite(upper):return np.nan,'uncertain'
    lo,hi=0.,float('inf')
    for x,y in zip(xs,ys):
        delta=previous_adj-y
        lo=max(lo,x+min((delta-2*eps)/lower,(delta-2*eps)/upper))
        hi=min(hi,x+max((delta+2*eps)/lower,(delta+2*eps)/upper))
    a,b=max(1,math.ceil(lo*100-1e-7)),math.floor(hi*100+1e-7)
    if b-a>200:return np.nan,'uncertain'
    candidates=[c/100 for c in range(a,b+1)
                if slope_bounds(xs+[c/100],ys+[previous_adj],eps) is not None]
    if len(candidates)==1:return candidates[0],'unique_adjusted_tick'
    return np.nan,'uncertain'

def public_calendar():
    dest=HERE/'extension-calendar.json'
    if dest.exists(): return json.loads(dest.read_text())
    url='https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh000001,day,2026-09-24,2026-11-24,120,'
    result=requests.get(url,timeout=15).json()
    dates=[r[0] for r in result['data']['sh000001']['day']]
    assert dates==sorted(set(dates)) and dates[-1]==END and dates[0]<=ARCHIVE_END
    dates=[d for d in dates if ARCHIVE_END<d<=END]
    dest.write_text(json.dumps(dates))
    return dates

def historical(con):
    con.execute("SET threads=4")
    con.execute("SET memory_limit='2GB'")
    con.execute("""
    create or replace table hist as
    select cast(date as date) date,code,try_cast(open as double) open,
    try_cast(high as double) high,try_cast(low as double) low,try_cast(close as double) close,
    try_cast(preclose as double) ref,try_cast(amount as double) amount,
    isST='1' as risk,tradestatus='1' and adjustflag='3' as trading
    from read_parquet('raw/bars_daily/*.parquet')
    where date between '2026-01-01' and '2026-09-24' and regexp_matches(code,?)
    """,[CODE_RE])
    duplicates=con.execute("select count(*) from (select date,code from hist group by date,code having count(*)>1)").fetchall()[0][0]
    assert duplicates==0

def extension(con):
    baseline=con.execute("""
       select code,arg_max(risk,date) risk,max(date) date
       from hist group by code
    """).df().set_index('code')
    records={}
    comparisons={}
    corporate_actions=0
    untrusted=[]
    codes=set()
    responded=set()
    known_codes=set(baseline[baseline.date.ge('2026-09-01')].index)
    source_rows=Counter()
    reference_rows={}
    ref_path=HERE/'sohu-references.json'
    direct=json.loads(ref_path.read_text()) if ref_path.exists() else {}
    dates=public_calendar()
    date_set=set(dates)
    for f in sorted((HERE/'extension').glob('*.json')):
        code=f.stem[:2]+'.'+f.stem[2:]
        data=json.loads(f.read_text())
        a=data['00']; b=data['02']
        if [x[0] for x in a]!=[x[0] for x in b]: continue
        previous_raw=None; previous_adj=None
        first=a[0][0] if len(a) else ''
        # For previously observed stocks, freeze the most recent known ST flag.
        # Later historical ST changes are not available from the extension bars.
        known=code in baseline.index and baseline.loc[code,'date']>=pd.Timestamp('2026-09-01')
        newly_listed=first>'20260924'
        if not known and not newly_listed:
            continue
        responded.add(code)
        risk=bool(baseline.loc[code,'risk']) if known else False
        for raw, adj in zip(a,b):
            day=f'{raw[0][:4]}-{raw[0][4:6]}-{raw[0][6:]}'
            try:
                op,hi,lo,cl,vol,amt=map(float,raw[1:7])
                ao,ah,al,ac,av,aa=map(float,adj[1:7])
                if not (min(op,hi,lo,cl,ao,ah,al,ac)>0 and amt>0 and vol>0 and lo<=min(op,cl)<=max(op,cl)<=hi):
                    continue
                if not math.isclose(amt,aa,rel_tol=1e-9,abs_tol=.01): continue
                reference,tag=confirmed_reference([op,hi,lo,cl],[ao,ah,al,ac],previous_raw,previous_adj,.0051)
                direct_row=direct.get(f'{f.stem}|{day}')
                if direct_row is not None:
                    q=[float(direct_row[i]) for i in (1,6,5,2)]
                    if all(abs(x-y)<.00001 for x,y in zip(q,[op,hi,lo,cl])):
                        reference=tick(cl-float(direct_row[3]));tag='quoted_change'
                if day>ARCHIVE_END and np.isfinite(reference) and reference!=previous_raw:
                    corporate_actions+=1
                if day in date_set:
                    records[code,day]=(day,code,op,hi,lo,cl,reference,amt,amt,risk,True,'ths')
                    reference_rows[code,day]=tag
                    codes.add(code)
                elif '2026-09-01'<=day<=ARCHIVE_END:
                    comparisons[code,day]=(day,code,op,hi,lo,cl,reference,amt)
                previous_raw=cl; previous_adj=ac
            except ValueError:
                untrusted.append((code,day))
    source_rows['ths']=len(records)
    crosschecks=[0,0,0]
    for f in sorted((HERE/'sohu').glob('*.json')):
        code=f.stem[:2]+'.'+f.stem[2:]
        rows=json.loads(f.read_text())
        first=min((r[0] for r in rows),default='')
        known=code in known_codes
        if not known and not first>ARCHIVE_END:
            continue
        responded.add(code)
        risk=bool(baseline.loc[code,'risk']) if known else False
        for r in rows:
            day=r[0]
            try:
                op,cl,change,lo,hi,vol,amt=map(float,[r[1],r[2],r[3],r[5],r[6],r[7],r[8]])
                ref=tick(cl-change)
                amt=amt*10000
                if not (min(op,cl,lo,hi,ref)>0 and amt>0 and vol>0 and lo<=min(op,cl)<=max(op,cl)<=hi):
                    continue
                if day in date_set:
                    key=code,day
                    if key in records:
                        a=records[key]
                        crosschecks[0]+=1
                        crosschecks[1]+=int(all(abs(a[i]-v)<.00001 for i,v in zip(range(2,6),[op,hi,lo,cl])))
                        crosschecks[2]+=int(abs(a[6]-ref)<.00001)
                    records[key]=(day,code,op,hi,lo,cl,ref,max(0,amt-50),amt+50,risk,True,'sohu')
                    reference_rows[key]='quoted_change'
                    codes.add(code)
                    source_rows['sohu']+=1
                elif '2026-09-01'<=day<=ARCHIVE_END:
                    comparisons[code,day]=(day,code,op,hi,lo,cl,ref,amt)
            except ValueError:
                untrusted.append((code,day))
    qq_comparisons=[]
    for f in sorted((HERE/'qq').glob('*.json')):
        code=f.stem[:2]+'.'+f.stem[2:]
        data=json.loads(f.read_text())
        known=code in known_codes
        if not known and not data['raw'][0][0]>ARCHIVE_END:
            continue
        risk=bool(baseline.loc[code,'risk']) if known else False
        responded.add(code)
        prev_raw=None;prev_adj=None
        for raw,adj in zip(data['raw'],data['hfq']):
            day=raw[0]
            if day!=adj[0]:continue
            try:
                op,cl,hi,lo,volume=map(float,raw[1:6])
                ao,ac,ah,al,_=map(float,adj[1:6])
                if not (min(op,cl,hi,lo,ao,ac,ah,al)>0 and volume>0):continue
                ref,tag=confirmed_reference([op,hi,lo,cl],[ao,ah,al,ac],prev_raw,prev_adj,.0006)
                direct_row=direct.get(f'{f.stem}|{day}')
                if direct_row is not None:
                    q=[float(direct_row[i]) for i in (1,6,5,2)]
                    if all(abs(x-y)<.00001 for x,y in zip(q,[op,hi,lo,cl])):
                        ref=tick(cl-float(direct_row[3]));tag='quoted_change'
                prev_raw=cl;prev_adj=ac
                lower=max(0,volume*100-100)*lo
                upper=(volume*100+100)*hi
                if day in date_set and (code,day) not in records:
                    records[code,day]=(day,code,op,hi,lo,cl,ref,lower,upper,risk,True,'qq-range')
                    reference_rows[code,day]=tag
                    codes.add(code)
                    source_rows['qq-range']+=1
                elif '2026-09-01'<=day<=ARCHIVE_END:
                    qq_comparisons.append((day,code,op,hi,lo,cl,ref,lower,upper))
            except ValueError:
                untrusted.append((code,day))
    cols=['date','code','open','high','low','close','ref','amount_lo','amount_hi','risk','trading','provider']
    ext=pd.DataFrame(records.values(),columns=cols)
    ext.date=pd.to_datetime(ext.date)
    overlap=pd.DataFrame(comparisons.values(),columns=[*cols[:7],'amount'])
    overlap.date=pd.to_datetime(overlap.date)
    assert not ext.duplicated(['date','code']).any()
    con.register('ext',ext)
    con.register('overlap_data',overlap)
    overlap_stats=con.execute("""
      select count(*),
          avg((abs(a.open-b.open)<.00001 and abs(a.high-b.high)<.00001 and
               abs(a.low-b.low)<.00001 and abs(a.close-b.close)<.00001)::int),
          avg((abs(a.ref-b.ref)<.00001)::int),
          median(a.amount/b.amount),avg((abs(a.amount/b.amount-1)<=.01)::int),count(a.ref)
      from overlap_data a join hist b using(code,date)
      where b.trading and b.amount>0 and not b.risk
    """).fetchall()[0]
    if qq_comparisons:
        qq_overlap=pd.DataFrame(qq_comparisons,columns=cols[:9])
        qq_overlap.date=pd.to_datetime(qq_overlap.date)
        con.register('qq_overlap',qq_overlap)
        qq_check=con.execute("""
          select count(*),avg((a.amount_lo<=b.amount and b.amount<=a.amount_hi)::int),
            avg((abs(a.open-b.open)<.00001 and abs(a.high-b.high)<.00001 and
                   abs(a.low-b.low)<.00001 and abs(a.close-b.close)<.00001)::int),
            avg((abs(a.ref-b.ref)<.00001)::int),count(a.ref)
          from qq_overlap a join hist b using(code,date)
          where b.trading and b.amount>0 and not b.risk
        """).fetchall()[0]
    else:qq_check=None
    directory=json.loads((HERE/'universe.json').read_text())['names']
    changed=[code for code in known_codes if code[3:] in directory and
             bool(baseline.loc[code,'risk'])!=('ST' in directory[code[3:]].upper())]
    audit={'codes':len(codes),'rows':len(records),'overlap_rows':overlap_stats[0],
           'OHLC_agree':overlap_stats[1],'reference_agree':overlap_stats[2],
           'median_amount_ratio':overlap_stats[3],'amount_within_1pct':overlap_stats[4],
           'inferred_ref_changes':corporate_actions,
           'untrusted_rows':len(untrusted),'source_rows_before_overlap':dict(source_rows),
           'target_known':len(known_codes),'known_source_responses':len(known_codes&responded),
           'known_no_response':sorted(known_codes-responded),
           'known_no_extension_trade':sorted(known_codes-codes),
           'status_changed_or_inconsistent_directory':sorted(changed),
           'crosschecks':[int(v) for v in crosschecks],
           'overlap_reference_observed':overlap_stats[5],
           'reference_types':dict(Counter(reference_rows.values())),
           'unknown_reference_rows':[(c,d) for (c,d),r in records.items() if not np.isfinite(r[6])]}
    audit['qq_overlap_check']=qq_check
    print('EXTENSION AUDIT',audit,flush=True)
    con.execute("create or replace table extension_bars as select * from ext")
    dateframe=pd.DataFrame({'date':pd.to_datetime(dates)})
    con.register('extension_calendar',dateframe)
    return audit

def wings(con, full):
    calendar_union=" union all select cast(date as date) from extension_calendar" if full else ""
    quote_union=" union all select cast(date as date),code,open,high,low,close,ref,amount_lo,amount_hi,risk,trading,provider from extension_bars" if full else ""
    con.execute(f"""
    create or replace table cal as
    select date,row_number() over(order by date)::integer seq
    from (select cast(calendar_date as date) date
    from read_parquet('raw/trade_calendar/*.parquet') where is_trading_day='1'
      and calendar_date between '2026-01-01' and '2026-09-24'
      {calendar_union})
    order by date;
    create or replace table prices as
    with merged as (select date,code,open,high,low,close,ref,amount as amount_lo,amount as amount_hi,risk,trading,'archive' as provider from hist {quote_union}), aged as (
        select b.*,c.seq,row_number() over(partition by code order by seq) obs,
          coalesce((b.trading and b.open>0 and b.close>0 and b.ref>0 and b.amount_lo>0 and b.risk is not null),false) as valid
        from merged b join cal c using(date)
    ), calculate as (
       select *,
       case when valid then close/ref-1 end ret,
       case when risk and date<'2026-07-06' then .05 else .10 end lim,
       coalesce(sum(case when valid then ln(close/ref) else 0 end)
         over(partition by code order by seq rows between unbounded preceding and 1 preceding),0) log_prev,
       median(case when valid then amount_lo end)
         over(partition by code order by seq range between 19 preceding and current row) liquidity
       from aged
    )
    select *,
      round(cast(round(ref*(1+lim)*100,8) as decimal(20,8)),0)/100 up,
      round(cast(round(ref*(1-lim)*100,8) as decimal(20,8)),0)/100 down,
      case when valid then exp(log_prev)*open/ref end adj_open,
      case when valid then exp(log_prev)*close/ref end adj_close
    from calculate;
    create or replace table quote as
    select code,date,seq,open,high,low,close,ref,amount_lo,amount_hi,ret,liquidity,
       ln(close/ref) logret,abs(close-up)<.00001 as board
    from prices where valid and not risk and obs>20;
    create or replace table streaks as
    with limits as (
      select code,seq,seq-row_number() over(partition by code order by seq) run
      from quote where board
    ) select code,seq,row_number() over(partition by code,run order by seq)::integer height from limits;
    create or replace table stockday as
    with share as (
      select q.*,amount_lo/sum(amount_hi) over(partition by seq) share_lo,
                 amount_hi/sum(amount_lo) over(partition by seq) share_hi,coalesce(s.height,0) height
      from quote q left join streaks s using(code,seq)
    ), stats as (
      select *,round(exp(sum(logret) over recent)-1,10) r5,
      count(*) over recent n_recent,count(*) over prior n_prior,
      sum(board::int) over recent boards5,avg(share_lo) over recent recent_lo,avg(share_hi) over recent recent_hi,
      avg(share_lo) over prior prior_lo,avg(share_hi) over prior prior_hi
      from share window recent as (partition by code order by seq range between 4 preceding and current row),
      prior as (partition by code order by seq range between 24 preceding and 5 preceding)
    ), ranked as (
      select *,rank() over(partition by seq order by r5 desc) market_rank,count(*) over(partition by seq) n_daily
      from stats where n_recent=5
    )
    select *,
      (height>=3 or (market_rank<=ceil(n_daily*.02) and boards5>=2)) as strict,
      market_rank<=ceil(n_daily*.1) and recent_lo>=prior_hi as broad
    from ranked where r5>0 and n_prior>=17 and
      (height>=3 or (market_rank<=ceil(n_daily*.02) and boards5>=2) or
      (market_rank<=ceil(n_daily*.1) and recent_lo>=prior_hi));
    """)
    daily=con.sql("""
    with d as (
      select t.seq,t.date,t.code,t.ret,t.board,
             coalesce(p.board,false) yesterday_board
      from quote t left join quote p on t.code=p.code and p.seq=t.seq-1
    ), q as (
      select seq,count(*) n,avg((round(ret,10)>0)::int) breadth,
        avg(ret) filter(where yesterday_board) premium,
        count(*) filter(where yesterday_board) prior_count,
        sum(board::int) boards,
        sum((board and yesterday_board)::int) promotions
      from d group by seq
    ), h as (select seq,max(height) height from streaks group by seq)
    select c.date,c.seq,q.*,coalesce(h.height,0) height,
       case when q.prior_count<10 then 'insufficient'
       when breadth>=.55 and round(premium,10)>0 then 'strong'
       when breadth<=.45 and round(premium,10)<0 then 'weak'
       else 'mixed' end regime
    from cal c left join q on c.seq=q.seq left join h on c.seq=h.seq order by c.seq
    """).df()
    # duplicate seq names arise from q.*, select explicit local sequence.
    daily=daily.loc[:,~daily.columns.duplicated()]
    return daily

def core_maps(con):
    scores=con.sql("""select * from stockday order by seq,r5 desc,code""").df()
    strict={}; broad={}; cohorts={}
    for day,g in scores.groupby('seq',sort=False):
        seq=int(day); picks=g[g.strict]
        strict[seq]=set(picks.code); broad[seq]=set(g[g.broad].code)
        top=picks.head(10)
        if len(top)==0:continue
        cohorts[seq]=(top.code.to_list(),float(top.recent_lo.sum()/top.prior_hi.sum()),
                      float(top.recent_hi.sum()/top.prior_lo.sum()),top.r5.to_list(),top.height.to_list())
    return strict,broad,cohorts

def reconstruct(daily, strict, broad, cohorts):
    episodes=[]
    ambiguous=[]
    current=None
    for row in daily.itertuples(index=False):
        seq=int(row.seq)
        if row.date<pd.Timestamp('2026-05-01'):
            continue
        if current is not None:
            retained=len(set(current['anchor']) & strict.get(seq,set()))
            threshold=math.ceil(len(current['anchor'])*.5)
            current['misses']=0 if retained>=threshold else current['misses']+1
            current['trajectory'].append({'seq':seq,'date':row.date,'retained':retained,'height':int(row.height)})
            if current['misses']>=2:
                current['end']=seq
                current['confirmed_exit']=True
                episodes.append(current)
                current=None
            continue
        anchor,ratio,ratio_max,r5,heights=cohorts.get(seq,([],0.,0.,[],[]))
        if len(anchor)>=3 and len(set(anchor)&strict.get(seq-1,set()))>=math.ceil(.6*len(anchor)):
            if ratio<1.3<=ratio_max:
                ambiguous.append({'date':str(row.date.date()),'ratio_lo':ratio,'ratio_hi':ratio_max})
            if ratio>=1.3:
                current=dict(start=seq,anchor=anchor,ratio=ratio,ratio_max=ratio_max,r5=r5,heights=heights,misses=0,
                         trajectory=[{'seq':seq,'date':row.date,'retained':len(anchor),'height':int(row.height)}],
                         end=None,confirmed_exit=False)
    if current is not None:episodes.append(current)
    return episodes,ambiguous

def price_maps(con,codes):
    con.register('selected_codes',pd.DataFrame({'code':sorted(codes)}))
    frame=con.sql("""select p.* from prices p join selected_codes s using(code) order by seq,code""").df()
    return {(row.code,int(row.seq)):row for row in frame.itertuples(index=False)}

def trade(prices, code, entry, exitseq, budget, signal_seq, last, slip=.001):
    p=prices.get((code,entry))
    anchor=prices.get((code,signal_seq))
    if entry>last:return {'status':'entry_pending','net':None}
    if p is None or not p.valid or p.risk or p.open>=p.up-.00001:
        return {'status':'entry_block','net':0.}
    if anchor is None or not np.isfinite(anchor.liquidity):return {'status':'liquidity_unknown','net':0.}
    limit=min(budget/(1+slip+.0003),(budget-5)/(1+slip),anchor.liquidity*.001)
    qty=int(limit/(p.open*100))*100
    if qty<=0:return {'status':'cash_or_liquidity','net':0.}
    cost=qty*p.open
    buy_fee=max(5,cost*.0003)+slip*cost
    if exitseq is None or exitseq>last:return {'status':'open','net':None}
    for seq in range(exitseq,min(exitseq+7,last+1)):
        x=prices.get((code,seq))
        if x is None or not x.valid or x.open<=x.down+.00001:continue
        if any((z:=prices.get((code,k))) is not None and z.trading and z.amount_lo>0 and not z.valid
               for k in range(entry,seq+1)):
            return {'status':'unknown_price_path','net':None}
        gross=cost*x.adj_open/p.adj_open
        sell_fee=max(5,gross*.0003)+(.0005+slip)*gross
        return {'status':'sold' if seq==exitseq else 'delayed','net':(gross-cost-buy_fee-sell_fee)/budget,'exit':seq}
    return {'status':'unresolved','net':None}

def metrics(trades):
    counts=Counter(t['status'] for t in trades)
    resolved=[x['net'] for x in trades if x['net'] is not None]
    return dict(status=dict(counts),signals=len(trades),resolved=len(resolved),
                net=float(np.mean(resolved)) if resolved else None,
                fills=sum(v for k,v in counts.items() if k in ('sold','delayed','open','unresolved','unknown_price_path')),
                positive=float(np.mean([r>0 for r in resolved])) if resolved else None)

def summarize(con,daily,eps,strict,broad):
    dmap=daily.set_index('seq').to_dict('index')
    last=int(daily.seq.max())
    cutoff=int(daily.loc[daily.date.ge(START),'seq'].min())
    use=[e for e in eps if (e['end'] is None or e['end']>=cutoff)]
    codes={c for e in use for c in e['anchor']}
    prices=price_maps(con,codes)
    directory=json.loads((HERE/'universe.json').read_text())['names']
    # Only for displaying stock names. Identifier selection uses no current names.
    name=lambda c:directory.get(c[3:],c)
    episodes=[]; pullbacks=[]; followers={10:[],30:[],60:[]}
    last_dip={}
    for e in use:
        a=e['anchor']; start=e['start']; end=e['end']
        members=[{'code':c,'name':name(c),'r5':r,'height':h} for c,r,h in zip(a,e['r5'],e['heights'])]
        strict_exit=end
        threshold=math.ceil(len(a)*.5)
        bmiss=0; broad_exit=None
        for t in range(start+1,last+1):
            count=len(set(a)&broad.get(t,set()))
            bmiss=0 if count>=threshold else bmiss+1
            if bmiss>=2:
                broad_exit=t
                break
        record={'start':str(dmap[start]['date'].date()), 'end':str(dmap[end]['date'].date()) if end else None,
            'strict_days':end-start if end else last-start+1,'duration_open':end is None,
            'broad_exit':str(dmap[broad_exit]['date'].date()) if broad_exit else None,
            'broad_days':broad_exit-start if broad_exit else last-start+1,
            'ratio':e['ratio'],'ratio_max':e['ratio_max'],'height':dmap[start]['height'],'regime':dmap[start]['regime'],
            'premium':dmap[start]['premium'],'breadth':dmap[start]['breadth'],
            'members':members,'trajectory':e['trajectory'],
            'first_warning':next((str(z['date'].date()) for z in e['trajectory'] if z['retained']<threshold),None)}
        for slip in (.001,.003,.006):
            results=[trade(prices,c,start+1,strict_exit+1 if strict_exit is not None else None,10000.,start,last,slip) for c in a]
            record[f'follow_{int(slip*10000)}']=metrics(results)
            if end is not None and start>=cutoff:
                followers[int(slip*10000)].extend(results)
        entryrows=[]
        # Fixed prior first-dip rule: drop 1-6%, previous day qualifies, no candidate within 4 sessions.
        for seq in range(max(start+1,cutoff),end if end is not None else last+1):
            for c in sorted(set(a)&strict.get(seq-1,set())):
                p=prices.get((c,seq))
                if p is None or not p.valid or not (-.06000001<=p.ret<=-.00999999):continue
                prior=last_dip.get(c,-100)
                last_dip[c]=seq
                if seq-prior<5:continue
                # Buy at T+1, exit T+4 open, as in the earlier fixed 3-session rule.
                x={'date':str(dmap[seq]['date'].date()),'code':c,'name':name(c)}
                for slip in (.001,.003,.006):
                    result=trade(prices,c,seq+1,seq+4,10000.,seq,last,slip)
                    x[f'trade_{int(slip*10000)}']=result
                prev=prices.get((c,seq-1))
                future=[prices.get((c,k)) for k in range(seq+1,seq+4)]
                unknown=any(z is not None and z.trading and z.amount_lo>0 and not z.valid for z in [p,*future])
                x['repair']= (bool(any(z is not None and z.valid and z.adj_close>=prev.adj_close*(1-1e-10) for z in future))
                             if seq+3<=last and prev is not None and prev.valid and not unknown else None)
                pullbacks.append(x); entryrows.append(x)
        record['pullback_signals']=len(entryrows)
        record['pullback_10']=metrics([x['trade_10'] for x in entryrows])
        episodes.append(record)
    return {'episodes':episodes,'pullbacks':pullbacks,'cohort_follow_10':metrics(followers[10]),
      'cohort_follow_costs':{str(b):metrics(rows) for b,rows in followers.items()},
      'pullback_costs':{str(b):metrics([x[f'trade_{b}'] for x in pullbacks]) for b in (10,30,60)},
      'repair':{'observed':sum(x['repair'] is not None for x in pullbacks),
          'repaired':sum(x['repair'] is True for x in pullbacks)},
      'daily':[{'date':str(r.date.date()),'height':int(r.height),'n':r.n,'breadth':r.breadth,'premium':r.premium,
                 'boards':r.boards,'promotions':r.promotions,'regime':r.regime} for r in daily.loc[daily.date.ge(START)].itertuples(index=False)]}

def encode(x):
    if isinstance(x, (np.integer,)):return int(x)
    if isinstance(x,(np.bool_,)):return bool(x)
    if isinstance(x,pd.Timestamp):return str(x.date())
    raise TypeError(type(x))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--full',action='store_true')
    args=parser.parse_args()
    con=duckdb.connect('full.duckdb' if args.full else 'archive.duckdb')
    historical(con)
    audit=extension(con) if args.full else None
    daily=wings(con,args.full)
    strict,broad,cohorts=core_maps(con)
    episodes,ambiguous=reconstruct(daily,strict,broad,cohorts)
    result=summarize(con,daily,episodes,strict,broad)
    result['ambiguous_onset_days']=ambiguous
    result['extension_audit']=audit
    Path('full-results.json' if args.full else 'archive-results.json').write_text(json.dumps(result,default=encode,ensure_ascii=False,indent=2))
    print(len(result['episodes']),result['cohort_follow_10'],result['pullback_costs'],result['repair'],flush=True)
