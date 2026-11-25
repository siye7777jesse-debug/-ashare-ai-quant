"""Environment-conditional factor study using the existing daily fill model."""
import json
from pathlib import Path
import sys

import duckdb
import numpy as np
import pandas as pd

from analyze import interval, label, simulate
from prepare import prepare

HERE = Path(__file__).resolve().parent
END = '2026-09-24'
FACTORS = ['concentration', 'relative_strength', 'persistence', 'limit_premium',
           'peer_follow', 'dip_support', 'promotion', 'unwind']
PERIODS = {
    '2019–2021': ('2019-01-01', '2021-12-31'),
    '2022–2023': ('2022-01-01', '2023-12-31'),
    '2024–2026H1': ('2024-01-01', '2026-06-30'),
    '2026Q3': ('2026-07-01', END),
}


def build(database, end):
    con = duckdb.connect(database)
    con.execute("SET threads=4")
    con.execute("SET memory_limit='3GB'")
    if 'research' not in {row[0] for row in con.execute('show tables').fetchall()}:
        prepare(con, end, persistent=True)
    con.execute((HERE / 'factors.sql').read_text())
    return con


def daily_corr(frame, columns):
    group = frame.date
    centered = columns - columns.groupby(group).transform('mean')
    cross = (centered.iloc[:, 0] * centered.iloc[:, 1]).groupby(group).sum()
    variance = centered.pow(2).groupby(group).sum().prod(axis=1)
    sizes = frame.groupby('date').size()
    return (cross / np.sqrt(variance.where(variance.gt(0)))).where(sizes.ge(5)).dropna()


def metrics(frame, factor, cal):
    selected = frame.loc[frame[factor].notna()].copy()
    selected['bucket'] = np.ceil(5 * selected.groupby('date')[factor].rank(pct=True)).astype(int)
    quotes = selected.dropna(subset=['forward'])
    pair = quotes[[factor, 'forward']]
    ic = daily_corr(quotes, pair)
    rank_ic = daily_corr(quotes, pair.groupby(quotes.date).rank())

    returns = selected.groupby(['date', 'bucket'])[['forward', 'net10', 'net30', 'net60']].mean()
    gross = returns.forward.unstack().reindex(columns=range(1, 6))
    spread = (gross[5] - gross[1]).dropna()
    top = selected.loc[selected.bucket.eq(5)]
    top_daily = top.groupby('date')[['net10', 'net30', 'net60']].mean()
    return {
        'signals': len(selected), 'ic_days': len(ic), 'ic': ic.mean(),
        'rank_ic': rank_ic.mean(), 'rank_interval': interval(rank_ic, cal) if len(rank_ic) else None,
        'buckets': gross.mean().to_list(), 'spread_days': len(spread), 'spread': spread.mean(),
        'top_net': top_daily.mean().to_list(), 'top_signals': len(top),
        'top_fill': top.execution.isin(['sold', 'delayed', 'unresolved']).mean(),
        'top_unresolved': int(top.execution.eq('unresolved').sum()),
    }


def join_disclosures(con):
    records = pd.read_json(HERE / 'disclosure-sample.json', convert_dates=False)
    if records.url.duplicated().any() or not records.url.str.startswith('https://static.cninfo.com.cn/').all():
        raise ValueError('Invalid example disclosure sources')
    con.register('disclosures', records)
    result = con.sql("""
        select d.code, d.published, d.category, d.url, min(c.date) as available,
               count(p.code) as candidate_days
        from disclosures d
        left join lateral (
           select date, seq from cal where date>cast(d.published as date) order by seq limit 5
        ) c on true
        left join factor_panel p on p.code=d.code and p.seq=c.seq
        group by all order by d.published
    """).df()
    assert (result.available > pd.to_datetime(result.published)).all()
    return result.to_dict('records')


def main(output):
    con = build('regimes.duckdb', END)
    panel = con.sql('select * from factor_panel order by date,code').df()
    cal = con.sql('select date from cal order by seq').df().date
    regime_rows = con.sql('select date,regime from state').df()
    outcomes = {'reports': {}, 'news': join_disclosures(con)}
    with build('prefix.duckdb', '2023-12-31') as past:
        truncated = past.sql('select * from factor_panel order by date,code').df()
        pd.testing.assert_frame_equal(
            panel[panel.date.le('2023-12-31')].reset_index(drop=True), truncated,
            check_exact=False, atol=3e-10, rtol=1e-8,
        )
        outcomes['prefix_rows'] = len(truncated)
    print('Prefix verified', outcomes['prefix_rows'], flush=True)
    for period, (start, end) in PERIODS.items():
        events, paths = label(con, panel, start, end)
        assert paths.bar_date.max() <= pd.Timestamp(end)
        opens = paths[paths.day_offset.isin([1, 4])].pivot(
            index='event_id', columns='day_offset', values='adj_open')
        events['forward'] = opens[4] / opens[1] - 1
        for bps in (10, 30, 60):
            fill = simulate(events, paths, bps / 10000)
            events[f'net{bps}'] = fill.net
            if bps == 10:
                events['execution'] = fill.execution
        days = cal[cal.between(start, events.date.max())]
        record = {'candidate_rows': len(events), 'first': events.date.min(), 'last': events.date.max(),
                  'states': regime_rows.loc[regime_rows.date.isin(days)].regime.value_counts().to_dict(),
                  'metrics': {}}
        for regime in ('all', 'strong', 'mixed', 'weak'):
            frame = events if regime == 'all' else events.loc[events.regime.eq(regime)]
            record['metrics'][regime] = {key: metrics(frame, key, days) for key in FACTORS}
        outcomes['reports'][period] = record
        print(period, len(events), flush=True)
    Path(output).write_text(json.dumps(clean(outcomes), ensure_ascii=False, indent=2, allow_nan=False))


def clean(value):
    if isinstance(value, dict):
        return {key: clean(item) for key, item in value.items()}
    if isinstance(value, list):
        return [clean(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.strftime('%Y-%m-%d')
    if isinstance(value, (float, np.floating)) and not np.isfinite(value):
        return None
    return value


if __name__ == '__main__':
    main(sys.argv[1])
