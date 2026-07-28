# WP-0012：账户差异处置与持续 OrderPlan/Shadow

- 版本：1.0.0
- 状态：已完成；真实本地状态等待已晋级 `PortfolioTarget`
- 需求：REQ-2026-0006 v1.2.0
- 阶段：4A～4B
- UI 提案：不适用；本工作包不新增或修改页面
- 券商授权：无新增授权；只消费 WP-0011 已保存的只读证据
- 日期：2026-07-28

## 目标

显式处理 WP-0011 发现的合成 Shadow 与 MiniQMT 模拟盘资金/持仓差异，在不把券商
未归属资产冒充战术分仓的前提下，让纯本地 OrderPlan 和跨日 Shadow 可以继续推进。

## 差异处置决定

- MiniQMT 模拟盘资金、持仓被分类为“隔离的外部模拟盘状态”，不导入 5 万元战术
  Shadow；
- 原有合成 50,000 元、空持仓 SQLite/WAL 账本继续是本地 Shadow 唯一权威；
- 处置只把 `local_shadow_allowed` 设为 `true`，`broker_actions_allowed` 永远为
  `false`；
- 未完成委托、实盘模式或非资金/持仓阻断不能使用该处置，必须继续失败关闭；
- 既有账户快照、对账报告和 Shadow 事件不修改、不删除、不重写。

该决定由用户 2026-07-28 指令“另建 REQ-2026-0006 工作包，处理本地 Shadow 与
券商模拟盘的资金/持仓起点差异，再推进持续 OrderPlan/Shadow”批准。

## 已实现

- 严格冻结的 `ReconciliationDisposition`、`ContinuousShadowState`、
  `DrawdownDecision`、`ShadowPlanLine` 和 `ContinuousShadowOrderPlan`；
- 追加式 SQLite 迁移 `0003`，保存差异处置、跨日状态检查点和 OrderPlan；
- `PortfolioTarget → OrderPlan` 确定性身份链、100 股整手、现金/最低佣金预留、
  T+1 可卖数量和次交易日起始约束；
- 8% 禁止扩大总风险、10% 冻结全部买入、12% 冻结买入并只生成清仓建议的本地判断；
- 纯本地行情驱动的 Shadow 成交、事件追加、状态检查点、重启恢复和次日 T+1 释放；
- `make continuous-shadow-initialize` 通过准确账户快照与对账报告身份执行幂等初始化。

## 实际初始化结果

- 差异处置身份：
  `reconciliation-disposition:b961fc7f8a3ae3f32829ea7d735df1b5e403a7193ba091fd940c47e241fba6de`；
- 本地状态身份：
  `continuous-shadow-state:ea689020c943c57f2ce2cfd6e4cd7c6c083b1d1eeafa39d82c9be47d254fb6d0`；
- `local_shadow_allowed=true`；
- `broker_actions_allowed=false`；
- REQ-2026-0005 已在本工作包完成后明确晋级反转/量价 10 日版；现有生产数据截至
  2026-07-24，不能冒充 2026-07-28 的新鲜信号，因此当前状态更新为
  `waiting_for_fresh_feature_snapshot_and_portfolio_target`，尚未生成订单计划或
  Shadow 成交。

## 验收

1. 模拟盘只有资金/持仓差异时可以形成确定处置；实盘、委托差异或身份错配失败关闭；
2. 处置后本地状态仍为 50,000 元空仓，券商持仓不会进入战术 Shadow；
3. 相同目标、状态、回撤判断和执行日期得到相同 `OrderPlan`；
4. 买入受现金和成本约束，卖出受 T+1 可用数量约束；
5. 8%/10%/12% 应用已批准动作，12% 不产生自动卖出事件；
6. Shadow 买入当日不可卖，下一交易日释放；重启恢复相同检查点；
7. SQLite 为 WAL，重复发布幂等、内容冲突阻断；
8. MiniQMT runner、`xttrader` 交易动作、Paper、Live、真实常设授权和 UI 均不在范围。

## 关闭与后续

WP-0012 的差异处置、持续 Shadow 核心、持久化和自动化证明已完成，可以关闭。
REQ-2026-0005 已完成准确晋级；真正的首个持续 Shadow 周期仍须从新鲜、不可变的
`FeatureSnapshot` 形成 `PredictionBatch → PortfolioTarget`，不得使用陈旧数据或
测试 Fixture 冒充生产目标。
