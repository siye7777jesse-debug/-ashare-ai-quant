"""Render the measured factor results into a phone-readable project report."""
import json
from pathlib import Path

NAMES = {
    'concentration': '资金集中度', 'relative_strength': '个股相对强度',
    'persistence': '抱团持续性', 'limit_premium': '同行涨停溢价',
    'peer_follow': '龙头带动代理', 'dip_support': '分歧承接代理',
    'promotion': '首板晋级率', 'unwind': '抱团瓦解代理',
}
STATES = {'all': '全部', 'strong': '强势', 'mixed': '混合', 'weak': '弱势', 'insufficient': '观测不足'}


def fmt(value, percent=False):
    if value is None:
        return '—'
    return f'{value:+.2%}' if percent else f'{value:+.3f}'


def render(result):
    reports = result['reports']
    recent = reports['2026Q3']
    lines = [
        '# 超短线抱团因子与市场环境',
        '',
        '这是第一轮首次分歧研究的延续。使用经 SHA-256 校验的公开沪深主板日线。',
        '先用当日上涨广度与昨日涨停股当日表现识别市场环境，再计算候选股票因子。',
        '本页的交易收益均为日线假设下的独立信号模拟，不能还原盘中排队或资金重叠。',
        '',
        '[研究工作流](workflow.md) · [因子定义及验证口径](v2-protocol.md) · '
        '[完整数字](v2-results.json) · [复算方法](reproduce.md)',
        '',
        '## 时间切分与截断验证',
        '',
        f"从原始数据删去 2023 年以后的行情重跑，前缀 {result['prefix_rows']:,} 个股票日的信号及因子匹配。",
        '各段尾部预留 10 个交易日，最长模拟卖出窗口留在本段。',
        '',
        '| 时段 | 信号日期范围 | 候选股票日 | 强势/混合/弱势/不足（天） |',
        '|---|---|---:|---:|',
    ]
    for period, data in reports.items():
        counts = '/'.join(str(data['states'].get(key, 0)) for key in ('strong', 'mixed', 'weak', 'insufficient'))
        lines.append(f"| {period} | {data['first']} 至 {data['last']} | {data['candidate_rows']:,} | {counts} |")
    lines += [
        '',
        '## 2026 年三季度复检',
        '',
        'IC 与 Rank IC 使用 T+1 开盘到 T+4 开盘的毛收益。每个交易日等权，每日至少五只有效股票。',
        '五档由信号日已知的因子值排序。最高档净收益使用单边 10 个基点滑点，含费用与无法入场的现金收益。',
        '高减低为毛收益分组差。它与最高档净收益使用不同口径。',
        '',
        '| 因子 | IC | Rank IC（天数） | Rank IC 95% 区间 | 高减低 | 最高档净收益 |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for key, m in recent['metrics']['all'].items():
        ci = ' 至 '.join(map(fmt, m['rank_interval'])) if m['rank_interval'] else '—'
        lines.append(f"| {NAMES[key]} | {fmt(m['ic'])} | {fmt(m['rank_ic'])}（{m['ic_days']}） | {ci} | "
                     f"{fmt(m['spread'], True)} | {fmt(m['top_net'][0], True)} |")
    for period in ('2024–2026H1', '2026Q3'):
        lines += ['', f'## {period} 各环境 Rank IC（有效交易日）', '',
                  '| 因子 | 强势 | 混合 | 弱势 |', '|---|---:|---:|---:|']
        for key, name in NAMES.items():
            values = [reports[period]['metrics'][state][key] for state in ('strong', 'mixed', 'weak')]
            scores = ' | '.join(f"{fmt(m['rank_ic'])}（{m['ic_days']}）" for m in values)
            lines.append(f'| {name} | {scores} |')
    lines += [
        '', '各组毛收益、三档滑点、最高档成交比例和未退出笔数见完整数字。'
        '区间按交易日分块抽样，未做多重检验校正。子组差异只用于形成待复核假设。',
        '', '## 消息面时间轴', '',
        '公告样本用于验证原件、发布日期和行情能否正确连接。由于缺乏完整公告覆盖，未用其计算消息因子 IC 或收益。',
        '',
        '| 股票 | 公告 | 披露日 | 最早标记日 | 后续五日候选数 |',
        '|---|---|---|---|---:|',
    ]
    for item in result['news']:
        lines.append(f"| {item['code']} | [{item['category']}]({item['url']}) | {item['published']} | "
                     f"{item['available']} | {item['candidate_days']} |")
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    result = json.loads(Path('v2-results.json').read_text())
    Path('v2-report.md').write_text(render(result))
