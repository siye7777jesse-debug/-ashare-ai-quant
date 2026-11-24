import duckdb

def prepare(con, end, persistent=False):
    temp='' if persistent else 'temp '
    con.execute("SET threads=4")
    con.execute("SET memory_limit='3GB'")
    con.execute(f"""
    create or replace {temp}table cal as
    select cast(calendar_date as date) as date,
           cast(row_number() over(order by calendar_date) as integer) as seq
    from read_parquet('raw/trade_calendar/*.parquet')
    where is_trading_day='1' and calendar_date between '2017-01-01' and '{end}';
    create or replace {temp}table membership as
    select cast(snapshot_date as date) as snapshot, code, code_name, industry
    from read_parquet('raw/industry_snapshots/*.parquet')
    where try_cast(updateDate as date) <= cast(snapshot_date as date)
      and industry is not null and length(trim(industry))>0;
    create or replace {temp}table mapped as
    select c.*, m.snapshot
    from cal c asof left join (select distinct snapshot from membership) m on c.date>m.snapshot;
    create or replace {temp}table base as
    select d.date, d.code, c.seq,
           try_cast(d.open as double) as open,
           try_cast(d.close as double) as close,
           try_cast(d.preclose as double) as ref,
           try_cast(d.amount as double) as amount,
           d.isST, d.tradestatus, d.adjustflag,
           m.industry, m.code_name,
           c.snapshot, d.date-c.snapshot as snapshot_age,
           row_number() over(partition by d.code order by d.date) as observations
    from (select cast(date as date) as date,* exclude(date)
          from read_parquet('raw/bars_daily/*.parquet')
          where date between '2017-01-01' and '{end}'
          and regexp_matches(code, '^(sh\\.60[0135][0-9]{{3}}|sz\\.00[0123][0-9]{{3}})$')) d
    join mapped c on d.date=c.date
    left join membership m on c.snapshot=m.snapshot and d.code=m.code;

    create or replace {temp}table series as
    with daily as (
      select *,
          (tradestatus='1' and amount>0 and open>0 and close>0 and ref>0
          and isST in ('0','1') and adjustflag='3') as traded,
          case when isST='1' then .05 else .10 end as lim
      from base
    ), px as (
      select *,
         cast(round(ref*(1+lim)*100, 6) as decimal(18,6)) as upper_cents,
         cast(round(ref*(1-lim)*100, 6) as decimal(18,6)) as lower_cents,
         case when traded then close/ref-1 end as ret,
         coalesce(sum(case when traded then ln(close/ref) else 0 end)
           over(partition by code order by seq rows between unbounded preceding and 1 preceding),0) as log_chain_prev
      from daily
    )
    select *,
        (traded and isST='0' and observations>20 and industry is not null and snapshot_age<=45) as eligible,
        (traded and close*100>=round(upper_cents)-.00001) as limit_close,
        (traded and open*100>=round(upper_cents)-.00001) as limit_open_up,
        (traded and open*100<=round(lower_cents)+.00001) as limit_open_down,
        case when traded then exp(log_chain_prev)*open/ref end as adj_open,
        case when traded then exp(log_chain_prev)*close/ref end as adj_close
    from px;

    create or replace {temp}table research as
    with d as (
      select *,
        round(adj_close / lag(adj_close,5) over (partition by code order by seq) - 1, 10) as r5,
        median(case when traded then amount end) over past_window as liquidity,
        lag(seq,5) over (partition by code order by seq) as prev5,
        sum(case when limit_close and eligible then 1 else 0 end) over five as boards5,
        lag(seq) over(partition by code order by seq) as prev_seq,
        lag(case when eligible then limit_close else false end) over(partition by code order by seq) as yesterday_board
      from series
      window past_window as (partition by code order by seq range between 19 preceding and current row),
             five as (partition by code order by seq range between 4 preceding and current row)
    ), industry_days as (
       select seq,industry, count(*) as members, sum(amount) as turnover,
              round(avg(r5),10) as rel_strength, avg(cast(coalesce(r5>0,false) as integer)) as breadth
       from d where eligible and seq-prev5=5 and r5 is not null
       group by seq,industry having count(*)>=15
    ), active as (
       select *, (row_number() over(partition by seq order by rel_strength desc,industry)
              <=ceil(count(*) over(partition by seq)*.20) and rel_strength>0) as top_industry
       from industry_days
    ), trends as (
       select *, sum(cast(top_industry as integer)) over(partition by industry order by seq range between 4 preceding and current row) as top_days
       from active
    ), share as (
       select d.*, trends.top_days, trends.top_industry, trends.breadth,
              d.amount/trends.turnover as amount_share,
              row_number() over(partition by d.seq,d.industry order by d.r5 desc,d.code) as leader_rank,
              trends.members
       from d join trends on d.seq=trends.seq and d.industry=trends.industry
       where d.eligible and d.seq-d.prev5=5 and d.r5 is not null
    )
    select *, round(avg(amount_share) over recent / nullif(avg(amount_share) over prior,0),10) as concentration,
           count(amount_share) over recent as n_recent, count(amount_share) over prior as n_prior
    from share
    window recent as (partition by code,industry order by seq range between 4 preceding and current row),
           prior as (partition by code,industry order by seq range between 24 preceding and 5 preceding);
    """)

def events(con, multiple, topdays):
    return con.execute("""
    with draft as (
      select cur.date, cur.seq, cur.code, cur.code_name, cur.industry, prev.r5 as prior_momentum,
         prev.concentration, prev.liquidity, prev.adj_close as pre_dip, cur.ret as dip,
         (prev.top_industry and prev.top_days>=? and prev.breadth>=.55) as lead_industry
      from research cur join research prev
        on cur.code=prev.code and cur.seq=prev.seq+1 and cur.industry=prev.industry
      where cur.ret between -.06000001 and -.00999999 and prev.leader_rank<=ceil(prev.members*.10)
        and prev.boards5>=1 and prev.concentration>=? and prev.n_recent=5 and prev.n_prior>=17
    ), firsts as (
      select *, lag(seq) over(partition by code order by seq) as prior_event from draft
    )
    select * from firsts where prior_event is null or seq-prior_event>=5 order by date,code
    """,[topdays,multiple]).df()
