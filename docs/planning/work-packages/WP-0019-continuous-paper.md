# WP-0019：持续 Paper、幂等恢复与盘后收敛

- 版本：1.0.0
- 状态：实现完成；真实模拟盘写入验收等待 WP-0018 确切限价最终批准
- 需求：REQ-2026-0010 v1.2.0
- 阶段：4E
- UI 提案：不适用；操作界面由 WP-0020 承接
- 日期：2026-07-28

## 目标

让获准的单笔 Paper `OrderPlan` 通过同一状态机完成提交前查询、一次提交、回调/查询事实、
未知状态恢复、限定撤单和本地投影收敛，同时确保进程重启或网络超时不会重复下单。

## 实现

- `PaperLimitProposal` 将窗口内 MiniQMT L1 卖一、确切0.01元限价、新鲜账户基线、
  Mandate 和源 PortfolioTarget 绑定；它自身始终不可提交；
- `PaperSubmissionApproval` 单独承载用户对准确数值限价和首次委托的最终批准；仓库当前
  没有创建该实例；
- `MiniQMTPaperGateway` 只接受 `simulation`，只使用普通股票 `FIX_PRICE`，提交前先按
  24字符确定性 `order_remark` 查询当日委托；
- 已存在相同备注时返回券商事实而不重提；提交调用超时进入 `submission_unknown`，
  后续只能查询恢复；
- 撤单在 Windows runner 内重新按相同备注定位唯一委托，只允许撤销本次金丝雀；
- 查询、提交和撤单结果脱敏为 `PaperBrokerCommandResult`，不保存账号、原始订单编号、
  用户目录或券商原始载荷；
- `ContinuousPaperExecutionService` 将命令结果归一为现有 `ExecutionEvent` 和
  `PaperOrderProjection`，处理确认、部分/全部成交、拒绝、撤单和未知恢复；
- 追加迁移 `0009_continuous_paper.sql` 保存限价提案、最终批准和券商命令证据；
- `make paper-canary-stage-limit` 顺序执行新的只读账户基线和单证券 L1 卖一读取，只发布
  待批准限价提案，不产生券商写入。

MiniQMT 调用形状依据迅投知识库的
[`order_stock`、`cancel_order_stock` 与查询接口](https://dict.thinktrader.net/nativeApi/xttrader.html)
实现；实际客户端仍以本机 `xtquant_250516` 验收为准。

## 安全边界

- 当前 Paper 意图、券商命令和券商观察数量仍为0；
- 不存在 `PaperSubmissionApproval`，因此没有代码入口可以通过最终提交检查；
- Live、信用、融资融券、期货、期权、市价单、异步重提和范围外撤单全部拒绝；
- 真实验收不能在 2026-07-29 09:35 前进行，也不能绕过用户对准确数值限价的最终批准。

## 自动化证据

- L1 超过3秒、窗口外、卖一上涨超过已批准限价、金额超限全部失败关闭；
- simulation 模式锁、提交前幂等查询和唯一备注；
- 第二次相同提交只查询，不再次调用写入；
- runner 源码不包含异步下单、信用接口或 Live 分支；
- SQLite/WAL 命令证据幂等追加，未知状态只能查询恢复；
- Paper 操作投影 API 不暴露账号、路径、Token 或秘密。

直接证据：

- [持续 Paper 与网关](../../../tests/unit/test_miniqmt_paper_gateway.py)
- [限价与最终批准边界](../../../tests/unit/test_paper_continuous.py)
- [脱敏操作投影 API](../../../tests/integration/test_paper_operations_api.py)

## 待真实日期完成

2026-07-29 09:35～09:45 内运行新的只读基线和 L1 限价提案，将准确委托摘要交给用户。
只有用户批准准确数值后才创建 `PaperSubmissionApproval` 并执行一次提交；随后验证券商
确认/成交或本单撤单、进程重启查询和盘后账户收敛。完成这些事实前，本工作包不能宣称
真实 Paper 周期验收完成。
