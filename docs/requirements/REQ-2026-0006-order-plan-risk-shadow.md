# REQ-2026-0006：订单计划、组合风险、Research Shadow 与 Local Replay

- 需求版本：2.1.0
- 状态：已批准；Research Shadow 新研究层和兼容迁移未实施
- 来源：2026-07-28 用户批准 REQ-0006 并推进 OrderPlan/Shadow；2026-07-29
  最终批准多候选 Research Shadow 与单账户 MiniQMT Paper 分层
- 目标阶段：阶段 4A～4D
- 实现状态：WP-0006、WP-0012～0014 已实现目标组合、OrderPlan、回撤门和本地
  确定性跨日账本；这些制品作为历史 Local Replay 证据保留。新的多候选 Research
  Shadow 和 MiniQMT Paper 虚拟分仓由 REQ-2026-0014/0010 承接，迁移尚未实施
- UI：现有 UI-PROP-0003/0006/0007/0008 没有表达新的研究/账户分层；需要新版本
  UI 提案获批后实施
- 追踪：见[需求索引唯一追踪表](./README.md#唯一追踪表)

## 目标

把已晋级策略产生的 `PortfolioTarget` 转换为可解释、可恢复的 `OrderPlan`，用
Local Replay 验证状态机、组合风险和恢复逻辑；让 Research Shadow 复用可执行语义
形成隔离的候选前向研究证据；券商执行和账户对账由 REQ-2026-0010 的 MiniQMT Paper
承接。

## 范围内

- 当前投影与目标组合之间的确定性订单差异；
- 现金、100 股整数手、T+1 库存、限价、交易窗口和撤单意图；
- 8%、10%、12% 回撤级别及各自明确动作；
- 常设授权模型和超限异常；
- Local Replay 的跨日调度、幂等恢复、持仓、现金、盈亏和故障演练；
- Research Shadow 的候选独立账本、登记后推进、同口径比较和研究归因；
- 兼容读取已有 Shadow 账本、检查点、事件和证据身份；
- 通过只读端口读取 MiniQMT 账户快照并为 Paper 启动对账提供输入。

## 范围外

- MiniQMT 模拟盘或实盘下单；
- 用 Local Replay 或 Research Shadow 结果授予 Paper 成熟度、券商成交质量或
  Paper/Live 权限；
- 创建未限定标的、金额、订单类型、时段、有效期和执行级别的常设授权实例；
- 自动批准超限订单；
- 信用、期货、期权或其他资产；
- 未批准的产品业务页面。

## 不变量

1. `PortfolioTarget → OrderPlan → ExecutionEvent` 身份链必须完整。
2. Local Replay 和 Research Shadow 都不产生券商副作用，也不累计 Paper 成熟度。
3. 陈旧行情、未知持仓、对账差异或风险规则缺失时失败关闭。
4. 常设授权内外必须可解释，不能使用一个无边界“自动交易”开关。
5. 回撤按分仓和账户总组合分别从已确认净值峰值计算；同时触发时执行更严格动作。
6. MiniQMT Paper 的完整模拟账户是唯一券商账户事实；不得被本地账本或虚拟分仓覆盖。
7. `StandingMandate` 的活动执行级别只能是 Paper 或经独立授权的 Live；兼容
   `ExecutionMode.SHADOW` 只允许读取历史制品或运行 Local Replay 测试。
8. 模拟盘未归属资金/持仓必须作为 `inherited` 进入账户风险或明确阻断；不能通过
   切换本地账本绕过。
9. 历史 Shadow 合成账本与 Paper 事件历史都保持不可变；新的 Research Shadow
   只能形成候选研究账本，不得成为第二个账户权威。
10. MiniQMT 不可用、账户模式未知或对账不平时，不得回退到本地假设成交并标记为
    Paper。

## 已冻结回撤动作

| 回撤 | 动作 | 允许 | 禁止 |
| --- | --- | --- | --- |
| 8% | 记录警告并进入风险受限状态 | 持有、减仓，以及不扩大总风险的计划调整 | 扩大分仓或账户总风险 |
| 10% | 冻结新开仓 | 持有或减仓 | 新证券开仓、扩大任何既有仓位 |
| 12% | 冻结全部买入并生成清仓建议 | 持有、人工决定后的后续动作 | 自动清仓、任何买入、把建议冒充已执行 |

回撤动作必须进入不可变风险判断和订单计划解释。12% 的清仓建议是
`Approval Exception`，在人工明确决定前不得转换成自动卖出订单。

## 常设授权边界

1. `StandingMandate` 必须记录策略版本、分仓、证券范围、金额/风险上限、订单类型、
   可执行时段、有效期、异常条件、MiniQMT 网关身份和准确执行级别。
2. 活动执行的 Paper、Live 是互斥执行级别；同一授权不能在运行时静默选择。
   `ExecutionMode.SHADOW` 仅为历史兼容和 Local Replay 测试，不能进入活动授权。
3. WP-0018 已创建的受限 Paper 金丝雀仍是独立历史授权事实；它不能自动扩展成短线、
   核心组合或 ETF 的持续 Paper 授权。
4. 产品方向批准、策略晋级和迁移代码都不等于授权连接 MiniQMT 或提交具体委托。

## Local Replay、Research Shadow 与 Paper 权威

- 已有 Shadow 合成 50,000 元账本保持不可变并改称历史 Local Replay 账本；
- Local Replay 可以重放订单计划、模拟部分成交、验证 T+1、风险和恢复，但不得产生
  Paper 成交、Research Shadow 前向研究或 Paper 成熟度；
- Research Shadow 为每个准确候选建立独立虚拟账本，只积累登记后新到达数据上的
  前向研究证据；候选之间不得共享现金、持仓和费用；
- Paper 按 REQ-2026-0010 v2.1.0 接管准确模拟盘账户的全部现金、持仓、委托和成交；
- Paper 按 REQ-2026-0014 在该唯一账户内维护短线/核心虚拟分仓和 managed 批次，
  但这些投影不得覆盖券商净事实；
- Paper 启动前已有持仓进入账户级风险，但不自动归因给策略；
- 三者复用可执行 `OrderPlan` 语义，但不复用账户或账本状态；
- Research Shadow 表现单独进入候选比较；Paper 交易日、成交质量和运营成熟度只从
  券商事实计算；
- MiniQMT 账户差异必须解决、接管为 `inherited` 或保持阻断，不能再以“隔离外部
  状态并继续本地 Shadow”解除 Paper 阻断。

## 验收标准

Given 相同目标、当前投影和配置，When 重复生成订单计划，Then 得到相同计划身份且不
重复写入事件。

Given Local Replay 在部分模拟成交后重启，When 重放事件账本，Then 恢复相同现金、
持仓和未完成计划，且 Research Shadow 证据和 Paper 成熟度都保持不变。

Given 行情陈旧、股票不可交易或对账不平，When 尝试推进计划，Then 生成明确阻断原因，
不得假设成交。

Given 订单超出未来常设授权，When 评估计划，Then 进入异常状态，不得静默执行。

Given 回撤达到 8%、10% 或 12%，When 生成或重新评估订单计划，Then 分别应用已冻结
动作，且更严格级别覆盖较低级别。

Given 回撤达到 12%，When 系统生成清仓建议，Then 建议可审计但没有卖出
`ExecutionEvent`，直至用户另行明确决定。

Given MiniQMT 账户快照与本地投影不同，When 完成启动对账，Then 保存脱敏差异并保持
券商动作阻断，Local Replay 历史不被重写且不能成为回退账户事实。

Given 一个新策略已经通过历史证据，When 尚未取得准确 Paper 授权或 MiniQMT 不可用，
Then 系统可以生成计划、Local Replay 测试和合法 Research Shadow 研究证据，但不得
标记为 Paper 运行或累计 Paper 成熟度。

Given 两个候选同时运行 Research Shadow，When 任一候选发生订单、费用或持仓变化，
Then 另一候选的完整虚拟现金和账本不变，比较仍披露各自失败与覆盖率。

## 历史持续 Shadow 制品

WP-0013、WP-0014 已形成 2026-07-27 目标、订单计划、跨日检查点和延迟日线回放。
WP-0029 也形成了最新数据到 Shadow `OrderPlan` 和离线 Paper 预检。这些身份和事实
不回写，统一解释为 Local Replay 历史证据；不得把它们追认为新的 Research Shadow、
形成 Paper Champion 或累计 Paper 成熟度。

代码中的 `continuous_shadow`、`shadow.py` 和 `ExecutionMode.SHADOW` 在迁移期保持
兼容读取和测试。删除或迁移必须由独立工作包证明历史制品可读、活动编排不再创建
SHADOW、Paper 不可用时失败关闭。

## 后续仍需精确化

- Local Replay/Shadow 兼容字段和 API 的退役周期；
- Research Shadow 的准确公共契约、账本存储和候选注册运行工作包；
- 短线、核心组合、ETF 各自 Paper `StandingMandate` 的准确范围；
- Paper 成熟度统计口径和续任/回退触发；
- 现有 UI 中 Shadow 操作的替换提案；
- 每次模拟盘写入、Live、首笔订单和 12% 清仓建议的独立资本动作决定。

## 版本历史

| 版本 | 日期 | 变更 | 状态 |
| --- | --- | --- | --- |
| 1.0.0 | 2026-07-27 | 从规划基线拆分 OrderPlan、风险与持续 Shadow 草案 | 需要澄清 |
| 1.1.0 | 2026-07-28 | 冻结三级回撤动作、常设授权模型边界和合成 Shadow 起点；批准 MiniQMT 只读账户对账工作包 | 已批准 |
| 1.2.0 | 2026-07-28 | 批准隔离模拟盘未归属状态、保留合成 Shadow 权威，并由 WP-0012 推进确定性 OrderPlan 与跨日 Shadow | 已批准并部分实现 |
| 1.3.0 | 2026-07-28 | 冻结 Shadow 合成账本与 Paper 完整模拟盘账户的双权威边界；不授权券商写入 | 已批准并部分实现 |
| 1.4.0 | 2026-07-28 | 冻结首份 Paper StandingMandate 与 inherited 重合处置；确切限价和实际提交继续分级批准 | 已批准并部分实现 |
| 2.0.0 | 2026-07-29 | 正式前向验证迁至 MiniQMT Paper；持续 Shadow 降级为兼容 Local Replay，历史身份不重写 | 已批准；迁移未实施 |
| 2.1.0 | 2026-07-29 | 新增独立候选 Research Shadow；Paper 保持唯一券商账户事实并由 REQ-0014 管理虚拟分仓 | 已批准；迁移未实施 |
