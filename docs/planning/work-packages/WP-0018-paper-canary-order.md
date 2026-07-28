# WP-0018：首份 Paper StandingMandate 与金丝雀委托

- 版本：1.0.0
- 状态：授权准备态已实现；等待确切限价与首笔委托最终批准
- 需求：REQ-2026-0010 v1.1.0、REQ-2026-0006 v1.4.0
- 阶段：4E
- UI 提案：不适用；本工作包只提供本地命令和不可变证据
- 日期：2026-07-28

## 已批准范围

- 执行级别仅为 MiniQMT `Paper simulation`，不得连接 Live；
- 准确证券 `605208.SH`，方向买入，数量 100 股，限价单；
- 战术分仓最大单笔名义金额 50,000 元；
- `StandingMandate` 有效期为 2026-07-29 09:30～10:00（Asia/Shanghai）；
- 唯一提交窗口为 09:35～09:45；
- 只允许一笔金丝雀委托；未确认时只查询恢复，禁止自动重提；
- 只允许撤销本次金丝雀委托；
- 与启动前 `inherited` 持仓重合时明确允许，但新增数量必须单独归因为 `managed`；
- 提交前生成的确切数值限价和首次 `order_stock` 调用必须再次获得用户明确批准。

## 本次实现

- 建立严格冻结的 `PaperCanaryAuthorization`，将准确 `PortfolioTarget`、Shadow
  `OrderPlan`、WP-0017 账户基线和公共 `StandingMandate` 绑定为一个内容身份；
- 将50,000元上限、唯一证券/方向/数量、有效期、提交窗口、行情新鲜度、未确认恢复、
  撤单范围和 inherited 重合处置写入不可变策略哈希；
- 首单准备态固定为 `awaiting_final_limit_approval` 和
  `broker_actions_allowed=false`，不能形成可提交 `PaperOrderIntent`；
- 追加 SQLite/WAL 迁移 `0008`，同一身份重复发布幂等、内容冲突阻断；
- 提供 `make paper-canary-authorize`，只发布本地授权证据，不启动 MiniQMT，不查询账户，
  不调用委托或撤单。

## A 股首单约束

本次金丝雀限定沪市主板普通 A 股，买入数量为100股，价格单位为0.01元。提交窗口避开
开盘集合竞价和不可撤单时段。提交前还必须重新检查 T+1、证券状态、停牌、ST/退市风险
警示、上市初期、涨跌停、交易所动态价格边界、卖一有效性、可用现金和账户风险。

规则依据为上交所、深交所当前交易规则及投资者教育说明：

- <https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml>
- <https://www.szse.cn/lawrules/rule/trade/current/t20260424_620190.html>
- <https://www.szse.cn/www/investor/index/update/t20230315_599240.html>

交易所规则只是提交前检查的一部分；券商实时拒绝或未知状态必须进入既有 Paper 状态机，
不能以本地检查通过替代券商事实。

## 剩余验收与最终批准

2026-07-29 的提交窗口内必须重新建立模拟盘模式锁和完整账户基线，确认没有外来挂单，
读取不超过3秒的 MiniQMT L1 卖一并生成0.01元精度的确切限价。系统随后只展示以下
最终摘要：

`证券、方向、数量、确切限价、最大可能金额、行情时间、账户/对账身份、Mandate 身份、
PortfolioTarget/OrderPlan 身份、撤单截止时间`。

在用户明确批准该摘要前，不调用 `order_stock`。若用户未确认、窗口关闭、行情陈旧、
卖一无效或任一预检失败，本工作包当日安全结束，不下单、不追价、不自动重提。只有首单
被批准并收到券商事实后，才验证确认、成交或唯一撤单闭环。

## 自动化证据

- 授权模型冻结、确定性身份与50,000元硬上限；
- 科创板、非整手、超额和越界时间窗口负例；
- SQLite/WAL 追加存储、幂等及往返读取。

本次真实本地发布结果：

- 授权：
  `paper-canary-authorization:3e548e6a4f6cb37ec155afbe71406018272fd38c6517a94848500ad91d556482`；
- StandingMandate：
  `standing-mandate:3a1787c14e97695c8adfeeb0d3a3e308f2e55258ce096d8ce1da5c784ed5ec37`；
- 源 PortfolioTarget：
  `portfolio-target:0410d6ff1d10676a99e9e88b38f11682c32c48ea085d414efec34757d4d2e1be`；
- 账户基线：
  `paper-account-baseline:a96048cdf9506f11075144a06159a73cd167b9f6b262709eed49b58ffcd443a8`；
- Paper 意图和券商观察数量均为0。

直接证据见
[test_paper_canary_authorization.py](../../../tests/unit/test_paper_canary_authorization.py)。
