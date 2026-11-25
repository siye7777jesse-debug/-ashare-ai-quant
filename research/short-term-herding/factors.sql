-- Market states use only the signal day's completed session.
create or replace table state as
with d as (
    select t.seq,t.date,t.code,t.ret,t.limit_close,
           coalesce(p.eligible and p.limit_close,false) as prior_board
    from series t
    left join series p on t.code=p.code and p.seq=t.seq-1
    where t.eligible
), market as (
    select seq,date,avg((round(ret,10)>0)::int) as breadth,
           avg(ret) filter (where prior_board) as premium,
           count(*) filter (where prior_board) as prior_count
    from d group by seq,date
)
select *,case
    when prior_count<10 then 'insufficient'
    when breadth>=.55 and round(premium,10)>0 then 'strong'
    when breadth<=.45 and round(premium,10)<0 then 'weak'
    else 'mixed' end as regime
from market;

-- Stock-day panel within the known regular main-board universe.
create or replace table factor_panel as
with members as (
    select r.*, coalesce(p.eligible and p.limit_close,false) as prev_board,
           coalesce(q.eligible and q.limit_close,false) as prev2_board
    from research r
    left join series p on r.code=p.code and p.seq=r.seq-1
    left join series q on r.code=q.code and q.seq=r.seq-2
), peer as (
    select *,
      sum(ret) over industry_day as peer_return_sum,
      round(avg(r5) over industry_day,10) as industry_r5,
      sum(case when prev_board then ret else 0 end) over industry_day as board_return,
      sum(prev_board::int) over industry_day as board_n,
      sum((prev_board and not prev2_board)::int) over industry_day as first_boards,
      sum((prev_board and not prev2_board and limit_close)::int) over industry_day as advanced
    from members window industry_day as (partition by seq,industry)
), lagged as (
    select *,
      lag(seq) over stock as preceding_seq,
      lag(r5) over stock as prev_r5,
      lag(industry_r5) over stock as prev_industry_r5
    from peer window stock as (partition by code,industry order by seq)
)
select l.date,l.seq,l.code,l.industry,l.liquidity,l.adj_close as pre_dip,s.regime,
       case when n_recent=5 and n_prior>=17 then concentration end as concentration,
       round(r5-industry_r5,10) as relative_strength,
       top_days as persistence,
       round((board_return-case when prev_board then ret else 0 end)
             / nullif(board_n-prev_board::int,0),10) as limit_premium,
       case when preceding_seq=seq-1 and prev_r5>prev_industry_r5 then
         round((peer_return_sum-ret)/(members-1),10) end as peer_follow,
       case when ret between -.06000001 and -.00999999 and high>low
            and close between low and high then round((close-low)/(high-low),10) end as dip_support,
       (advanced-(prev_board and not prev2_board and limit_close)::int)::double /
         nullif(first_boards-(prev_board and not prev2_board)::int,0) as promotion,
       case when preceding_seq=seq-1 then
         round((prev_r5-prev_industry_r5)-(r5-industry_r5),10) end as unwind
from lagged l join state s using (seq)
where l.date >= '2019-01-01' and boards5>=1 and leader_rank<=ceil(members*.20)
order by date,code;
