# 2026 年 7 月至 11 月抱团研究复算

工作目录为本文件所在目录。Python 3.12，依赖使用上一轮研究的 requirements.txt，另安装 requests。本轮只使用价格、成交量、成交额及股票交易状态。所有公开请求无需用户上传 CSV 或持有付费 API。

## 原始输入

- 2026-09-24 及之前的日线使用 FREE_DATA_v0 原始归档。下载 URL 为 https://github.com/noblechang/a-share-data/releases/download/FREE_DATA_v0/a-share-raw-v0.tar ，SHA-256 为 9e5d9d7386f695f5b255b4d44adb435aec410c5df4276f8db44be111deed0d35。
- 解包时排除 macOS 元数据文件，使用 `tar --exclude='._*' -xf snapshot.tar`。原始行情放在 raw 目录。
- 后续行情由公开同花顺 K 线（00 为原价，02 为后复权）、搜狐历史行情（收盘价、涨跌额、成交额）及腾讯 K 线（原价、后复权、成交量）补齐。腾讯上证指数日线只提供后续交易日历。
- 仓库根目录 data/stocks.json 用于显示名称和补充归档没有覆盖的股票代码。股票日线与前一日集合决定信号，后来的名称仅作展示。本轮使用的根目录数据版本见本 PR 的基准提交。
- 若只有腾讯成交量，成交额范围为当日成交股数乘最低价至最高价，另留一手误差。既有市场成交额总范围和个股金额范围推导出份额及集中倍数范围。仅在下界达到 1.30 时确认。搜狐金额按万元两位小数换算并留 50 元四舍五入误差。
- 2026-09-24 后的每日 ST 状态未完全获得；归档中已有证券采用其当时最后已知状态。本轮用后来的目录状态进行单独敏感性检查。新上市证券按已观察日线数量限制，仍需补齐逐日证券状态及特殊价格限制规则。

## 运行

已保存的公开输入缓存可直接复算。需要重新采集时，依次运行以下命令。遇供应商限流时脚本停止该来源，后续来源作独立补充。发布到仓库的是代码、报告及统计结果，不含第三方原始行情文件；在线数据更新、接口可用性、复权版本差异可能导致重采集结果变化。

1. `python prepare_universe.py`
2. `python analyze_cycles.py`（先计算至原始快照截止日期）
3. `python collect_ths.py`
4. `python collect_sohu.py`
5. `python collect_remaining.py`
6. `python ref_audit.py`
7. `python ref_fetch.py`
8. `python analyze_cycles.py --full`
9. `python validate.py`
10. `python -m unittest -v test_episodes`

禁止将缺失成交额当作已知值；不存在可靠前收盘参考的交易日不得作为有效信号。复权价格通过当日 OHLC 与前一交易日收盘的线性相容性判断是否需要确认新的前收盘，若不能确定唯一价格刻度且无真实涨跌额，则该交易日无有效前收盘。单笔成交跨越无法核实的价格路径时保持收益未知。

结果原始 JSON 为 full-results.json，截断及敏感性检查为 validation.json。报告采用本次采集的数据结果。
