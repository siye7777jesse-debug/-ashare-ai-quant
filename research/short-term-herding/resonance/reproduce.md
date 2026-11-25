# 复算板块共振周期

使用上一轮研究准备的原始公开历史快照及 full.duckdb、archive.duckdb。先按照 ../episodes/reproduce.md 准备数据，再从 episodes 目录运行。

- `python ../resonance/group_cycles.py full.duckdb ../resonance/results.json --prefix full-theme-panel.pkl`
- `python ../resonance/group_cycles.py archive.duckdb prefix-theme-results.json --end 2026-09-24 --prefix prefix-theme-panel.pkl`
- `python ../resonance/verify_prefix.py full-theme-panel.pkl prefix-theme-panel.pkl`
- 在 resonance 目录运行 `python -m unittest -v test_resonance`。

报告所列任意日期领涨股可从 group_cycles.build 建立的临时 members 表按 cohort、date 筛选，按 stock_log5 降序和 code 升序排序。完整结果含五类代理的逐日数据、预设参数敏感性及全部历史行业已结束周期。输入期间内的日线和行业数据来源、局限及复权处理见上一轮说明。
