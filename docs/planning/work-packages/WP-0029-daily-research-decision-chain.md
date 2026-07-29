# WP-0029：最新数据到本地研究决策链与安全预检

- 版本：1.0.0
- 状态：已批准并实现
- 需求：REQ-2026-0005 v1.0.0、REQ-2026-0006 v1.4.0、REQ-2026-0009 v1.1.0、
  REQ-2026-0010 v1.1.0
- 上游：WP-0025 v1.1.0 的已提交日度管线身份
- 阶段：3C、4、6C
- UI 提案：不新增页面或布局；只在已批准的 UI-PROP-0003/0007/0008 状态区域显示
  只读进度、结果与恢复动作
- 日期：2026-07-28
- 券商授权：无；Paper 派发固定禁用，不连接 MiniQMT

## 目标

从 WP-0025 已提交的准确 `DataSnapshot` 出发，确定性生成并保存：

```text
DataSnapshot
→ FeatureSnapshot
→ PredictionBatch
→ OptimizationProblem / OptimizationResult
→ PortfolioTarget
→ OrderPlan (Shadow)
→ 本地 Shadow / Paper 预检
```

整条链使用已晋级的准确策略版本和封存证据，只形成研究与执行准备证据，不启动新的
持续 Shadow 周期，不模拟成交，不连接券商，也不提交或撤销 Paper/Live 订单。

## 范围

- 读取唯一的日度管线提交指针，不读取运行中的中间 `current`；
- 验证 `DataSnapshot` 中股票日线、统一派生复权价和逐日可交易状态的最后交易日；
- 要求研究输入日期等于预期最近完成交易日；行业更新较新但股票输入落后时失败关闭；
- 精确读取已晋级的 `StrategyVersion`、`PromotionDecision` 和封存证据；
- 复用冻结的反转/量价 10 日信号、特征、预测和战术 50,000 元组合逻辑；
- 生成 Shadow `OrderPlan`，但不调用 `start_cycle` 或任何成交模拟；
- 运行本地离线安全预检，固定
  `paper_dispatch_state=disabled`、`broker_actions_allowed=false`；
- 产物按内容身份只追加保存，最后原子切换决策链当前指针；
- 保存步骤检查点；同一输入中断后恢复，不重复产生逻辑身份；
- API 和现有界面只读显示输入日期、各薄腰身份、状态、阻断和恢复动作。

## 非目标与保护边界

- 不调用 MiniQMT、`XtQuantTrader`、账户、资金、持仓、委托或成交接口；
- 不提交、撤销或查询恢复任何模拟盘订单；
- 不启动或推进持续 Shadow 周期，不产生 `ExecutionEvent`；
- 不创建或激活新的 `StandingMandate`；
- 不训练、调参或重新晋级策略；
- 不进入长线模型、行业生命周期或 ETF；
- 不把旧股票日线伪装为最新：数据未齐时允许 WP-0025 成功而本工作包明确阻断。

## 确定性与恢复

- 运行身份由日度管线提交身份、准确 `DataSnapshot`、策略版本、晋级决定、信号日和
  编排策略版本共同决定；
- 决策时间使用输入快照的可审计 `as_of`，不使用重跑墙上时间改变内容身份；
- 每一步只引用上一步不可变身份；落盘前重新验证薄腰契约；
- 同一运行身份下已有内容不同即阻断，绝不覆盖；
- 中断恢复从最后一个完整检查点继续；完成后的相同输入直接返回相同产物；
- API 只暴露脱敏身份、日期、状态和恢复动作，不暴露候选行情值、账户或订单载荷。

## 预检口径

### Shadow

- 本地持续 Shadow 起点必须已经存在；
- 回撤规则继续使用 REQ-2026-0006 冻结的 8%/10%/12% 动作；
- 只评估计划状态与阻断，不启动周期，不生成成交。

### Paper

- 本工作包只生成离线预检结果；
- 备份/恢复、数据新鲜度、身份链和风险预览必须可见；
- `paper_dispatch_state` 永远为 `disabled`；
- `broker_actions_allowed` 永远为 `false`；
- 既有金丝雀授权、提交窗口或历史 Paper 状态不被本工作包修改。

## 运行状态

- `waiting_data`：WP-0025 尚无完整提交；
- `running`：持有本地租约并从检查点推进；
- `current`：身份链完整且预检已落盘；
- `blocked`：数据陈旧、策略/证据漂移、Shadow 起点缺失、风险或身份冲突；
- `recovery_required`：存在未完成运行和安全检查点；
- `no_action`：链完整，但目标组合不产生订单差异。

## 验收

1. Given 股票研究输入落后于日度管线预期日期，When 运行，Then 状态为 `blocked`，
   不生成伪造的最新特征或订单计划。
2. Given 同一准确数据、策略和起点，When 独立运行两次，Then
   `FeatureSnapshot → PredictionBatch → PortfolioTarget → OrderPlan` 身份完全一致。
3. Given 任一步骤后模拟进程中断，When 使用同一运行身份恢复，Then 从检查点继续，
   已完成产物不变且没有券商调用。
4. Given 晋级决定、证据或当前策略定义不一致，When 运行，Then 失败关闭并显示脱敏
   阻断码。
5. Given 预检完成，When 检查产物、日志、API 和页面，Then 均显示
   `broker_actions_allowed=false`、`paper_dispatch_state=disabled`，无账户和订单载荷。
6. Given API 或页面刷新，When 上游有运行中或失败任务，Then 只读取状态投影并提供
   恢复命令，不在请求路径联网或重算研究链。

## 检查

```text
uv run pytest tests/unit/test_daily_decision_chain.py
uv run pytest tests/integration/test_daily_pipeline_api.py
make check
make e2e-smoke
git diff --check
```

真实联网只属于 WP-0025；WP-0029 的验收消费其不可变产物，不额外连接数据或券商。

## 授权记录

用户在 2026-07-28 的持续目标中明确要求新建并实施 WP-0029，并明确排除模拟盘提交、
撤单、Live、真实交易日等待、长线模型、生命周期与 ETF。任何越过这些边界的动作都
需要新的独立授权。

## 实施结果

2026-07-28，WP-0029 消费 WP-0025 的 2026-07-27 准确提交，形成：

- `FeatureSnapshot`：
  `feature-snapshot:d8211bbfc2eedf2463095576c64bdde4ce39d00a6ca608ab16c55620f08387f1`；
- `PredictionBatch`：
  `prediction-batch:5f3bd7f65dbad0e55ffef82307d6eb72da4805b7a6161dfe817dcb3edc156f65`；
- `PortfolioTarget`：
  `portfolio-target:5b84e19396be000ca4410169634ba07628b6e4a08c5ef15d4d94c3d999b82240`；
- Shadow `OrderPlan`：
  `order-plan:c3ac7b75ffae5b3aeb360dcd707c039fb208827585e0c013069b0b82145dde6f`；
- Shadow 与离线 Paper 预检均为 `ready`，但
  `paper_dispatch_state=disabled`、`broker_actions_allowed=false`。

决策制品哈希为
`sha256:614f08d163c33ca0fe97cfec46fc68e19ebccac887e388a971ddc6f34f3c90fe`。
制品不含 `cycle`，实现没有调用 `start_cycle`、MiniQMT 或券商接口；相同输入重跑
0.51 秒返回同一身份。重跑前后本地既有 `continuous_shadow_cycles=1`、
`shadow_events=4` 均未变化，证明本工作包没有推进历史 Shadow 周期或生成执行事件。
缺少上游提交、研究输入日期落后以及晋级证据漂移分别形成可见的
`waiting_data`、`blocked/research_inputs_stale` 和
`blocked/decision_prerequisite_invalid`，不会在状态投影建立前静默失败。

最终自动化验收：

- `make check`：160 个 Python 测试、12 个前端测试以及格式、lint、类型、生产构建、
  架构、文档、密钥、规模和 10 个公共契约 Schema 全部通过；
- `make e2e-smoke`：5 个浏览器工作流全部通过，系统页可见日度数据与决策链状态，
  且不存在提交、撤单、买入或卖出按钮；
- `git diff --check`：通过。
