# WP-0016：Paper 执行状态机、幂等与离线端口合同

- 版本：1.0.0
- 状态：实现完成
- 需求：REQ-2026-0010 v1.0.0
- 阶段：4E
- UI 提案：不适用；UI-PROP-0003/0006/0007/0008 v0.1 仍待批准
- 券商授权：无；不连接 MiniQMT，不读取账户，不提交或撤销委托
- 日期：2026-07-28

## 目标

在完全离线且不接触券商 SDK 的前提下，冻结 Paper 股票限价委托的领域语义、幂等身份、
单调状态机、恢复查询端口和 SQLite/WAL 追加证据链，为后续单独授权的只读握手建立
可测试边界。

## 实现

- 严格冻结的 `PaperOrderIntent` 只接受 `ExecutionMode.PAPER`、A 股证券代码、买卖方向、
  正价格和 100 股整数手，并绑定 `OrderPlan`、合成预检决策和确定性幂等键；
- `PaperBrokerObservation` 将确认、部分/全部成交、拒绝、撤单请求、已撤及未知状态归一
  为 broker-neutral `ExecutionEvent`，只保存脱敏券商指纹和序号；
- 状态投影处理重复、乱序、迟到和撤单/成交竞争；累计成交不能减少或超过委托数量，
  已成交、已拒绝等矛盾证据失败关闭；
- `submission_unknown` 的唯一恢复动作是按幂等键查询事实，投影始终
  `retry_permitted=false`，服务层没有委托或撤单提交入口；
- 离线合成适配器实现查询端口；任何命令端口调用均明确拒绝；
- 追加迁移 `0006_paper_offline.sql`，分别保存意图、观察和不可变投影；同一身份内容冲突
  阻断，重复内容幂等，进程重启后可重放恢复；
- `Paper` 内部契约通过 Trading Execution 的 `public.py` 暴露，不泄漏券商类型、Windows
  路径、账户标识或秘密。

## 状态规则

`prepared → submission_unknown/acknowledged/rejected`；
确认后可进入 `partially_filled`、`cancel_pending`、`cancelled` 或 `filled`。
低于已见券商序号的证据只增加审计计数，不改变事实投影；撤单等待中发生全部成交时以
`filled` 收敛。未知状态在事实查询没有给出新证据时保持未知，不能直接重提。

## 验收证据

- 契约冻结、额外字段、Paper 模式、A 股代码和整手限制；
- 十项提交前检查及阻断；
- 确定性意图和幂等键；
- 重复、乱序、迟到、累计成交异常、终态冲突与撤单竞争；
- 未知状态只查询一次事实，合成适配器命令调用数保持零；
- SQLite/WAL 追加存储、内容冲突、重启读取和确定性重放；
- 源码扫描证明本工作包没有券商 SDK、交易 API、账户标识或本机路径引用。

直接证据见
[test_paper_execution_offline.py](../../../tests/unit/test_paper_execution_offline.py)。

## 非目标与下一步

- 不连接或启动 MiniQMT 交易会话，不注册真实回调；
- 不读取新的模拟盘账户快照，不创建真实 `StandingMandate`；
- 不调用任何委托或撤单接口，不启用 Paper 金丝雀或 Live；
- 不实现业务 UI；
- 下一安全工作是 WP-0017。它仍需用户单独授权“模拟盘只读握手和回调生命周期”，
  并且只能验证账户模式、完整基线及只读回调，不能下单或撤单。
