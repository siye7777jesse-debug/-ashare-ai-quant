# 超短线抱团研究工作流

1. **Deep Research 查原始证据。** 在 ChatGPT 中开启 Deep Research，附上本目录的 `v2-protocol.md` 和最近一期报告。用下方提示词交付带链接的数据证据表。
2. **GPT-6.2 高级推理审研究口径。** 在支持该模型的模型选择器使用 GPT-6.2 Astra 或 Sol 的较高推理设置。把证据表交给模型，请它区分因果假设与可观测代理、找未来数据入口、检查弱市样本数量、给出预注册阈值与停止条件。将最终研究口径保存到仓库，在查看新留出结果前冻结。
3. **Codex 跑真实数据和研究测试。** 校验输入快照与日期，按研究口径生成可复算结果，跑截断测试和成交测试，经 PR 审阅。研究结果可以否定假设。收益只由代码按行情计算。

## Deep Research 提示词

> 研究沪深普通主板超短线抱团。优先核查交易所规则、巨潮法定披露、日线数据源、题材历史成分能否追溯。围绕资金集中、相对强度、持续性、涨停溢价、龙头带动、分歧承接、首板晋级和瓦解，列出每个因子的最早可见时点和对应的原始字段。为公告源核查历史覆盖、证券代码、首次披露时间、修订文档、缺失和使用条件。逐条附原链接，并区分公开数据能做的检验和需要分钟或逐笔数据的部分。不要生成收益。输出 Markdown，交给 GPT-6.2 审核并交给 Codex 实现。

## 本轮的实际执行

本轮使用公开网页检索核验证据，由 Codex 实现和计算。Deep Research 与 GPT-6.2 模型选择是仓库中的交接步骤。本轮没有单独启动 Deep Research 任务，也未从仓库调用模型 API。

- [Deep Research 官方说明](https://help.openai.com/en/articles/10500283-research-faq)
- [GPT-6.2 在 Work 和 Codex 中的选择方式](https://help.openai.com/en/articles/20001275-chatgpt-work-and-codex)
- [公开行情输入与快照覆盖](https://github.com/noblechang/a-share-data)
- [沪市 2026 年 7 月风险警示涨跌幅规则](https://www.sse.com.cn/aboutus/mediacenter/hotandd/c/c_20260424_10816474.shtml)
- [深市 2026 年交易规则](https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html)
