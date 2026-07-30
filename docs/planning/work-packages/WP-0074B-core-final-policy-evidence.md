# WP-0074B：核心最终 O0、晋级证据与 CorePolicy

- 版本：1.0.0
- 状态：已授权，依赖门等待 WP-0073B 集成
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5C、5D
- UI 提案：不适用
- 所有者：后续核心政策工作树 / Strategy Research 与 Portfolio & Risk 接桥

## 目标

复用 WP-0074A 唯一成本/O0/账本语义，对 B0、Ridge 和 WP-0073B LightGBM 做最终
样本外比较，形成 H20/H60 各自的 eligible 候选、三级参照证据、十桶校准生产门、
固定 50%+50% 联合 O0、弱信号/系统失效状态机，以及可由后续显式人工决定准确绑定的
`CorePolicyVersion`。

本包只生成 broker-free 候选、决策草稿和研究组合目标。它不替用户选择候选，不创建
StandingMandate、公共 OrderPlan、MiniQMT Paper/Live 或真实订单。

## 启动门

1. WP-0073A、WP-0074A、WP-0073B 全部集成；
2. 每个 LightGBM 候选绑定 WP-0074A 槽位和同配置 Ridge 父级；
3. 所有候选拥有完整滚动 OOF、季度模型、校准、C0～C3 订单/NAV 和共同排除账本；
4. 2023～2025 名单在回放前冻结，回放途中无动态递补；
5. 工作树从最新主线建立，Portfolio & Risk/Trading Execution 高争用文件无并行修改。

## 非目标

- 不训练或重选特征、Ridge、LightGBM、模板、alpha 或校准器；
- 不修改 WP-0074A 的费用、O0、账本、容量或执行时钟；
- 不自动 Promotion/Renewal/Fallback，不形成候选总分或自动 champion；
- 不运行 Research Shadow，不追认历史回放为前向证据；
- 不创建 UI，不运行生产训练/激活，不连接 MiniQMT；
- 不读取账户，不创建 StandingMandate、Paper/Live 或订单；
- 不提前实现 CMM、注意力、CVaR/MVSK、预测融合或动态周期权重。

## 允许文件与上下文边界

- `src/astramind_mini/strategy_research/core/policy_evidence/**`
- `src/astramind_mini/portfolio_risk/core_weekly/**`
- `tests/unit/test_core_policy_evidence_*.py`
- `tests/unit/test_core_weekly_target_*.py`
- `tests/golden/test_core_policy_evidence.py`
- `tests/fixtures/core/policy/**`
- 本工作包及直接追踪状态

Strategy Research 拥有候选、历史/OOF 证据、lineage、参照和人工决定语义；Portfolio &
Risk 只拥有确定性联合目标、持仓/行业/现金约束和风险覆盖。两者通过本包内最小不可变
输入 DTO 接桥，Portfolio & Risk 不导入 `strategy_research.core` 内部模块。

不得修改根 `contracts/**`、现有 PortfolioTarget、OrderPlan、Trading Execution、
Data、`composition.py`、数据库迁移、前端或生产 `var/`。若最终公共接入确需扩展薄腰，
停止并由主控另建单所有者合同提交。

## 制品与四层身份

本包形成：

- `CoreHorizonEligibilityEvidence`；
- `CoreReferenceSet`；
- `CoreLineageEvidenceVersion`；
- `CorePolicySelectionInput`；
- `CorePolicyVersion`；
- `CoreWeeklyTargetDraft`；
- `CoreSignalStateRecord`；
- `CorePromotionDecisionDraft`。

身份层固定为：

1. `StrategyLineage`：因子/selected、模型配方和周期；
2. `StrategyVersion`：准确季度模型产物；
3. `LineageEvidenceVersion`：全部真实历史折产物及证据；
4. `CorePolicyVersion`：准确 H20/H60 版本、各 50%、O0、成本、约束和状态机。

当前模型不能回填历史。季度重训只创建新 StrategyVersion；特征清单、alpha/模板或训练
配方变化创建新 lineage。所有制品用规范 JSON/SHA-256，绑定上游模型、校准、账本、
费用、参照、排除账本、决策输入和代码身份。

## H20/H60 候选预算

每周期研究候选最多：

- 永久 R0/B0；
- 一个 WP-0074A 冻结的 Ridge 决赛者；
- 一个通过本包 LightGBM 相对父级增量门的挑战者。

LightGBM 对同配置 Ridge 使用相同周末、C2、O0、起始现金和共同排除账本；H20/H60
分别用 4/12 周圆形移动区块、10,000 次。只有配对 `ΔCAGR_pp` 分布第 10 百分位严格
大于 0 才进入候选预算。失败后不启用亚军。

“R0 / B0”是同一候选，不重复计算。所有 eligible 候选都可供后续人工选择；基线或
挑战者标签不是权限。

## 周度 RankIC 与覆盖

每个周度决策日以当日点时 U0 计算预测与成熟主标签 Spearman RankIC，平均秩并列：

- 标签覆盖不少于当日 U0 的 95%，否则该周无效；
- 平均 RankIC `>= 0.02`；
- RankIC 为正的有效周占比 `>= 55%`；
- Q5-Q1、单调性、ICIR、指数/行业/市场状态只作诊断。

候选特有缺失不得删除；计划周有效覆盖低于 95% 时证据无效。系统性无效周只能按共同
排除账本从候选和参照同时删除。

## 三级参照与 Horizon 晋级门

硬参照按候选当时状态准确生成：

- R0：首次选择非 R0 lineage 的永久硬参照；R0 自身豁免；
- incumbent：替换在位版本时的硬参照；
- direct parent：增加复杂度时的硬参照。

精确重复只比较一次。每个 H20/H60 新 lineage 必须：

1. C2 整段净收益 `> 0`；
2. 两项 RankIC 门通过；
3. 对每个有效硬参照，`P(ΔCAGR > 0) >= 90%`；
4. 对每个有效硬参照，原始样本 `ΔCAGR_pp >= 2`。

Horizon 层不叠加年度、MDD、Calmar 或换手硬门。任何参照缺准确同窗证据时失败关闭，
不能由人工跳过。

配对 bootstrap 使用共同交易日逐期收益，H20 4 周、H60 12 周、10,000 次；种子为
候选证据 ID、参照证据 ID、周期和成本版本拼接后 SHA-256 前 64 位大端无符号整数。
每次重采样分别复利；任一单期收益 `<= -1` 失败关闭。

## 校准生产门

WP-0073A/B 的校准必须同时满足：

- 只使用滚动 OOF；
- 至少 156 个有效周度截面且十桶各至少 30 个样本；
- 最高桶拟合收益严格高于十桶拟合收益中位数；
- 使用该候选的最终受约束篮子，完整往返 C2 预期净收益严格大于 0；
- 校准未到下一计划季度重训日，模型/特征/方向身份兼容。

通过后从 `statistically_ready` 转为 `production_valid`。失败、陈旧或方向检查失败时
禁止新增风险，没有宽限期。

## H20/H60 联合 O0

每周期预算固定 50,000 元：

- `sum(w20) <= 0.5`；
- `sum(w60) <= 0.5`；
- `w_final = w20 + w60`；
- `cash = 1 - sum(w_final)`。

任一周期失效时该 50% 留现金，不转给另一周期。对每只证券：

`score_5d_H = exp((5/H) * ln(1 + expected_net_return_H)) - 1`

最终排序为 `0.5 * score_5d_H20 + 0.5 * score_5d_H60`；失效或不支持的周期贡献为 0
且预算留现金，不重标权重。最多选择五只；每周期只向自身分数严格为正且进入最终名单
的证券等额分配自身预算。

最终组合必须：

- 0～5 只，目标 5 只；
- 单股 `<= 25%`；
- SW L1 `<= 40%` 且最多两只；
- 100 股整数手；
- 预留准确费用；
- 每个净额单边订单通过 0.1% 容量门；
- 不可行部分留现金。

先合并同一证券 H20/H60 贡献和净额，再做整数手、费用、容量与约束修复。修复只允许
减少目标股数、减少数量或增加现金；每次修复后重算全部约束，禁止向剩余证券归一化。

## Top5/Top10 与边际成本

- 新增风险要求最终 Top5 且受约束篮子 C2 预期净收益 `> 0`；
- 已持股票在 Top10 内继续持有，不做机械漂移再平衡；
- 旧股跌出 Top10、替代者在 Top5 且替换边际 C2 `> 0` 才可主动替换；
- 每周最多一次自愿替换，首次建仓豁免；
- 风险退出、不可交易恢复和强制处置不占自愿替换额度；
- 新买计完整预期往返费用；持有不重复计已发生买入成本；
- 替换比较继续持有与卖旧买新的增量路径。

## 信号状态机

H20/H60 分别维护：

| 状态 | 条件 | 研究动作 |
| --- | --- | --- |
| `ACTIVE` | 连续确认的有效强信号 | 可新增/调整风险 |
| `WEAK_PENDING` | 首个系统健康但 C2 门失败周 | 不新增，已有贡献不主动退出 |
| `RETREATING` | 连续第二个有效弱信号周 | 每周最多退出一个自愿仓位 |
| `RECOVERY_PENDING` | 退让后首个有效恢复周 | 停止退让但不新增 |
| `SYSTEM_INVALID` | 数据/模型/校准/方向/管线失效 | 冻结，不更新强弱计数 |

第二个连续有效恢复周回到 ACTIVE。系统失效不能伪造卖出；组合/账户级风险可独立减少
风险。只有一个周期失效时，只移除其贡献，另一周期保持。

## 联合 CorePolicy 硬门

准确选择的 H20/H60 版本组合成一个候选政策后必须：

1. C2 整段净收益 `> 0`；
2. 三个完整日历年中至少两年 C2 净收益 `> 0`；
3. 对每个有效硬参照，`P(ΔCAGR > 0) >= 90%` 且原始 `ΔCAGR_pp >= 2`；
4. 对每个参照，三个完整年中至少两年相对收益 `> 0`；
5. C2 日度可执行 NAV MDD `< 12%`，Calmar `>= 0.5`；
6. 年化单边换手 `<= 500%`；
7. 全部最终订单通过容量、费用、现金和执行门。

单年相对落后超过 5pct 只标黄色诊断，不是额外硬门。联合 CorePolicy 只比较 incumbent；
各模型 direct parent 留在 Horizon 层，避免重复门。

## Promotion、Renewal 与 Fallback

本包只构造并验证 `CorePromotionDecisionDraft`：

- Promotion：新 lineage 首次取得资格，绑定准确 StrategyVersion、证据、校准和参照；
- Renewal：同 lineage 新季度版本，C2 总收益正且
  `P(ΔCAGR >= -1pct) >= 90%`，并通过联合风险/校准；
- Fallback：只能回到兼容 R0 或 prior champion，记录原因，只检查自身绝对门。

用户后续一次原子选择准确 H20/H60 版本；新版本失败但旧版本有效则保留旧版，两者无效
则对应预算现金。系统不生成跨周期版本笛卡尔推荐，不自动确认任何草稿。

## Golden 与负向证明

fixture 覆盖三完整年、两个周期、R0/Ridge/LightGBM、incumbent/direct parent，并包括：

- RankIC 0.02、55%、标签覆盖 95% 和共同排除边界；
- 4/12 周区块、10,000 次、概率 90%、原始 +2pct；
- LightGBM 第 10 百分位增量正/零/负；
- 校准 156 周、每桶 30、最高桶、中位数、C2 与到期；
- 50%+50%、单周期现金、同证券净额、25%/40%、100 股和容量修复；
- Top5/Top10、边际成本、一次替换和五态转换；
- 2/3 年、MDD、Calmar、500% 换手和黄色单年落后；
- Promotion/Renewal/Fallback 身份缺失、参照错配、自动确认和未来回填负测。

bootstrap、CAGR/MDD/Calmar、组合修复和状态机使用独立 oracle。金额/数量/状态/原因/
身份/哈希精确相等；比率使用 `atol=rtol=1e-12`。

## 验收

1. 每周期只开放 R0、最多一 Ridge、最多一合格 LightGBM，失败不递补。
2. RankIC、参照、bootstrap、C2 和校准门逐项可审计且候选缺失不能美化。
3. H20/H60 固定各 50%，失效留现金；最终约束和修复不归一化。
4. Top5/Top10、边际成本、两周弱化/恢复和系统冻结通过状态转移负测。
5. Horizon 与联合硬门不重复，Promotion/Renewal/Fallback 参照准确。
6. CorePolicy 必须由显式准确选择输入形成，无法自动选择或跨周期笛卡尔推荐。
7. 只生成 broker-free 研究目标，不创建 OrderPlan、StandingMandate 或券商动作。
8. 上游、成本、数据、参照、决定或代码变化必须重标识，未来数据不改旧证据。

## 检查

```text
uv run pytest tests/unit/test_core_policy_evidence_*.py \
  tests/unit/test_core_weekly_target_*.py tests/golden/test_core_policy_evidence.py -q
uv run pytest tests/unit/test_core_o0_costs_*.py tests/unit/test_core_o0_ridge_*.py \
  tests/unit/test_core_lightgbm_*.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/policy_evidence \
  src/astramind_mini/portfolio_risk/core_weekly tests/unit/test_core_policy_evidence_*.py \
  tests/unit/test_core_weekly_target_*.py tests/golden/test_core_policy_evidence.py
uv run mypy --strict src/astramind_mini/strategy_research/core/policy_evidence \
  src/astramind_mini/portfolio_risk/core_weekly
make docs-check
git diff --check
```

## 授权与交接

主控分别复核 Strategy Research 证据和 Portfolio & Risk 联合目标边界，通过后才释放
WP-0075 的 broker-free Research Shadow 接桥。WP-0075 仍需公共 Shadow 合同依赖，
不会由本包自行进入运行。

本授权不包含新 UI、生产训练/激活、生产补采、MiniQMT、账户、StandingMandate、
Research Shadow 实际运行、Paper/Live 或订单。
