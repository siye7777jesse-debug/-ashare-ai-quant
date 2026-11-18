# A股双引擎量化研究平台

手机网页版（GitHub Pages）与免费历史数据研究原型。

## V3 开发中
- `index.html`：单股策略研究、CSV导入、优先读取 `data/<股票代码>.json`、同期买入持有对照。
- `update_data.py`：通过公开东方财富K线接口获取六只A股的不复权日线数据；失败时不会编造数据。
- `.github/workflows/update-data.yml`：在默认分支定时执行，也支持在 GitHub Actions 手动触发。成功时提交 `data/*.json`。
- `test_update_data.py`：离线解析单元测试，使用构造的测试输入，不会把测试数据发布为真实行情。
- `.github/workflows/test-data.yml`：PR代码测试。

## 发布与运行
1. 先审查并合并开发分支到 `main`，GitHub Pages 才会使用新版网页。
2. 到 GitHub Actions 运行 **Refresh public A-share history**，确认真实数据采集成功、仓库出现 `data/*.json`。
3. 打开网站，选择配置过的股票代码，数据方式选择“GitHub自动更新历史数据”。
4. 若GitHub Actions无法访问第三方数据源，需调整采集方案；不能假定采集必然成功。

## 研究限制
仅支持六只股票的示范性单股回测。数据不复权，未覆盖退市证券、完整停牌/涨跌停撮合、逐日历史税费、分红、存活偏差与组合资金管理。策略研究功能不等于已完成AI自主策略发现，不构成投资建议。
