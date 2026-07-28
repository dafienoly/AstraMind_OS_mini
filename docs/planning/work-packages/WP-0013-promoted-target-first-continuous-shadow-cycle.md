# WP-0013：晋级策略新鲜目标与首个持续 Shadow 周期

- 版本：1.0.0
- 状态：实施中；身份链已生成，首周期等待 2026-07-29 开盘
- 需求：REQ-2026-0005 v1.0.0、REQ-2026-0006 v1.2.0
- 阶段：4B
- UI 提案：不适用；本工作包不新增或修改页面
- 券商授权：无；纯本地 Shadow，`broker_actions_allowed=false`
- 日期：2026-07-28

## 目标

把生产数据更新至最近完成交易日，用已明确晋级的准确策略与证据生成
`FeatureSnapshot → PredictionBatch → PortfolioTarget → OrderPlan`，并启动首个可恢复的
持续 Shadow 周期。

## 边界

- 只使用不可变生产 `DataSnapshot` 和准确晋级决定；
- Tushare 仅用于只读市场数据及未来交易日历；
- 候选证券与行情明细只保存在 Git 忽略的 `var/` 证据目录；
- 不读取新的 MiniQMT 账户事实，不连接交易端口，不调用下单或撤单；
- 不启用 Paper、Live 或真实常设授权；
- 已经错过的名义开盘不得用盘中价、收盘价或事后价格伪造成交。

## 实现

- 最终 H4 数据快照覆盖证券主表、交易日历、日线、复权因子、估值与交易约束、历史
  名称/ST/可交易状态，以及统一派生复权价格；
- 当前信号扫描沿用封存回放的相同反转/量价 10 日规则、股票池和可交易性约束；
- 精确核对晋级账本、证据包、单项证据和 `StrategyVersion`，任一身份漂移即失败关闭；
- 新增确定性 `FeatureSnapshot` 与当前 `PredictionBatch` 生成；
- 从排序候选构建 5 万元战术分仓的两持仓 `PortfolioTarget`；
- 复用 WP-0012 的现金、整手、最低佣金、T+1 和三级回撤规则生成 `OrderPlan`；
- 新增追加式迁移 `0004` 和 `ContinuousShadowCycle`，记录名义执行日、计划执行日、
  等待状态及错过名义开盘的原因；
- `make continuous-shadow-start` 是显式联网与本地状态变更命令，不进入 `make check`。

## 本次生产身份

- 最近完成交易日：2026-07-27；
- 数据快照：
  `snapshot:sha256:4766ebb03e7c759e377221e4093a75ffb20e91ad9c385c6d4f8720465ac49dc7`；
- 特征快照：
  `feature-snapshot:f14055b0fbc8523f44f1fde75ec858b22a3e0ddebbdb517a39aaf6350dae114f`；
- 预测批次：
  `prediction-batch:095c3240a91e6df159d5b306cb6ab9cde979ab30d866c06503fd1edb93d50b31`；
- 目标组合：
  `portfolio-target:0410d6ff1d10676a99e9e88b38f11682c32c48ea085d414efec34757d4d2e1be`；
- 订单计划：
  `order-plan:0d0a841fcbfd70632c99efd0005df3ab08bb2a7b1fe571ab58d880d40925d61c`；
- 持续 Shadow 周期：
  `continuous-shadow-cycle:3a373acf1c5c4bb6f2182e4ae2c37a7c81b51efb0984a91b43f5944758ebf589`。

扫描得到 86 个符合规则的候选，目标组合取排序前两项；订单计划有两行、状态
`ready`，没有现金或风险阻断。完整候选和行情值只保存在本地忽略目录。

## 时间语义与当前状态

2026-07-27 收盘信号的名义执行日是 2026-07-28，但最终 H4 快照在当日
10:18（Asia/Shanghai）形成，09:30 开盘已经错过。因此：

- 名义执行日：2026-07-28；
- 计划执行日：2026-07-29；
- 周期状态：`waiting_next_open`；
- 警告：`nominal_next_open_missed`；
- 当前订单计划没有对应 `ExecutionEvent`；
- `broker_actions_allowed=false`。

只有在 2026-07-29 有新鲜、可交易且未触及价格限制的本地行情时，才能由 Shadow
撮合推进；否则保持等待或记录明确阻断，不能假设成交。

## 已完成检查

- 同一命令连续执行两次，六个身份与周期状态完全一致；
- SQLite 中该订单计划和周期仍各一条，该计划的 `ExecutionEvent` 数为 0；
- `make check` 通过：82 项 Python 测试、4 项 Web 测试、类型、架构、文档、密钥、
  构建和 10 个公共契约 Schema 漂移检查全部通过，总耗时 21.03 秒；
- `git diff --check` 通过；`var/`、密钥、真实行情制品和 `NUL` 均未进入 Git 差异。

## 验收与关闭条件

1. 快照最新日与信号日均为 2026-07-27；
2. 晋级策略、证据包和单项证据身份完全匹配；
3. 重复输入生成相同的特征、预测、目标、订单计划和周期身份；
4. 订单计划只使用 `ExecutionMode.SHADOW`，券商动作始终为假；
5. 错过 2026-07-28 开盘只产生等待和警告，不产生该计划的成交事件；
6. 追加式存储重复发布幂等、内容冲突阻断、重启可读；
7. 2026-07-29 首次撮合后保存事件与状态检查点，或保存可解释的未成交/阻断证据；
8. 完成一个 10 交易日观察周期后再关闭本工作包，不把 Shadow 结果称为 Live 表现。
