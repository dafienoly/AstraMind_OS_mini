# WP-0006：短线目标组合与本地 Shadow

- 状态：已完成本地执行基线
- 需求：REQ-2026-0001 v1.0.1
- 完成日期：2026-07-27
- 券商授权：无
- UI：未实现；UI-PROP-0006/0007/0008 仍待批准

## 已实现

- 5 万元 tactical 分仓，最多两只，现金是合法目标；
- 通过 `OptimizationProblem → OptimizationResult → PortfolioTarget` 形成公共身份链；
- 目标与当前股数转换为 100 股整手的 Shadow `OrderPlan`；
- 本地行情驱动的全成、部分成交、无行情、陈旧行情和不可交易拒绝；
- 按佣金、最低佣金和印花税投影非负现金、持仓均价与已实现盈亏；
- 通过公共 `ExecutionEvent` 记录结果；
- SQLite/WAL 追加式 Shadow 事件账本，支持重启恢复、相同事件幂等和内容冲突阻断。

## 受保护边界

实现没有导入 MiniQMT 交易模块，没有账户标识、常设授权实例、Paper 或 Live，也没有
真实订单。日度对账、长时调度和产品页面仍属于后续 Shadow 运行工作包。
