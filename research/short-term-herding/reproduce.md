# 复算超短线抱团研究

研究使用公开发布的 FREE_DATA_v0 原始快照。日线价格和股票状态来自该快照里的 BaoStock 数据，行业来自月末证监会行业快照。原始归档的 SHA-256 为 9e5d9d7386f695f5b255b4d44adb435aec410c5df4276f8db44be111deed0d35。

[数据来源与下载](https://github.com/noblechang/a-share-data/releases/tag/FREE_DATA_v0)

在 Python 3.12 环境运行 `python -m pip install -r requirements.txt`。如需完整复算，在本目录解开 a-share-raw-v0.tar 中的 raw 目录，再运行 `python analyze.py`，生成 results.json 和 event-results.jsonl.gz。运行 `python render_report.py` 生成 report.md。第一次需要扫描日线和月度行业文件。若替换数据源，需要先清除本脚本产生的 computed-2026-06-30-v2.duckdb 和 prefix 开头的 DuckDB 缓存。

成交规则单元测试使用内置的模拟价格，不需要下载历史行情。运行 `python -m unittest -v test_execution`。

口径与执行细节见 protocol.md。event-results.jsonl.gz 保留主口径逐事件结果和 10 个基点的模拟成交结果。事件日期是分歧信号日，前三日中任何一次恢复到分歧前收盘才记为收盘修复。因停牌或缺少有效价而无法观察的收盘不记为修复，缺失天数单独保留。实际成交从下一交易日开盘开始，零成交事件保留为零收益。金额按每笔模拟预算 1 万元归一化。数据快照和复算材料无需连接交易账户。
