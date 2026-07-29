---
status: superseded
superseded_by: ADR-0008
supersedes:
  - ADR-0002
  - ADR-0005（仅 supersede 本地 Shadow 继续作为独立晋级级别的部分）
---

# ADR-0007：MiniQMT Paper 是唯一正式前向验证环境

> 已由 ADR-0008 替代。下文保留 2026-07-29 的历史决定；当前架构重新引入独立
> Research Shadow 作为多候选前向研究证据，但不把它作为券商账户或 Paper 成熟度。

## 背景

仓库原来把无券商副作用的本地撮合称为 Shadow，把 MiniQMT 模拟账户执行称为
Paper，并要求策略先通过本地 Shadow 再进入 Paper。这会同时维护两套账户权威、
运行成熟度和晋级状态，也使本地假设成交与券商真实模拟成交产生不必要的语义竞争。

## 决定

正式策略晋级链统一为：

`历史回测/封存回放 → MiniQMT Paper → 经独立授权的 Live`

MiniQMT Paper 是唯一正式前向验证环境。它使用准确 `simulation` 账户的完整现金、
持仓、未完成委托和成交事实，并通过同一套 `PortfolioTarget → OrderPlan →
ExecutionEvent` 契约运行。

原本的本地 Shadow 不再是执行级别、晋级门槛、冠军状态或运营成熟度来源。其已有
确定性撮合、跨日账本和延迟日线能力保留为 `Local Replay`，只用于：

- 领域与执行状态机测试；
- 故障注入和恢复演练；
- 回测/封存证据复核；
- MiniQMT 不可用时解释本应生成的计划，但不得据此累计正式前向表现。

已有 `ExecutionMode.SHADOW`、Shadow 账本和历史证据身份在兼容期内保持可读，不重写
历史；新业务流程不得再创建新的正式 Shadow 冠军或成熟度。迁移完成后，活动运行只
允许 `PAPER` 或经单独授权的 `LIVE`。

## 约束

- 本决定批准产品与架构方向，不授权连接 MiniQMT、调用 `order_stock`、撤单或启用
  Live。
- 每个 MiniQMT Paper 写入仍必须处于准确 `StandingMandate`、模式锁、启动对账、
  新鲜行情、风险限制和幂等恢复边界内。
- MiniQMT 不可用、账户模式未知、对账不平或回调状态未知时失败关闭；系统不得退回
  本地模拟成交并把它冒充 Paper 证据。
- Paper 与 Live 继续使用独立、准确的执行级别；Paper 证据不能自动授权 Live。

## 结果

系统只维护一套正式前向账户事实和成熟度，减少双账本、双状态机和双晋级语义。代价是
正式前向观察依赖本机 MiniQMT 模拟环境可用；离线开发与故障测试仍由 Local Replay
承担，但不再具有晋级权威。
