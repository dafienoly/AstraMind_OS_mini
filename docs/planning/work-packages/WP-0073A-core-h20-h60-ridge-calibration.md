# WP-0073A：核心 H20/H60 B0/Ridge、滚动预测与绝对收益校准

- 版本：1.2.0
- 状态：已授权，依赖门等待 WP-0072 集成
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5C
- UI 提案：不适用
- 所有者：后续核心模型工作树 / Strategy Research

## 目标

消费 WP-0072 冻结的 `full/selected`、跨包联合特征视图和公共前向标签，建立 H20、H60
完全独立的周度学习链第一段：五年滚动训练、季度重训、B0 永久锚点、Ridge 主比较、滚动样本外
预测、十桶 isotonic 绝对收益校准，以及绑定环境和上游身份的安全模型制品。

本包发布 B0/Ridge 候选及其样本外预测证据，不自行宣布最终赢家。WP-0074A 使用准确
C2 成本与 O0 从中冻结每周期 Ridge 决赛者和最多四个 LightGBM 父级槽；WP-0073B
只训练这些槽，WP-0074B 再完成最终比较与唯一 `CorePolicyVersion`。该分段消除
“LightGBM 槽等待 O0、O0 又等待 LightGBM”的循环依赖。

## 启动门

1. WP-0071A/B/C 与 WP-0072 均已由主控复核并集成；
2. 三包 `full`、H20/H60 `selected` 及每周期三个 pair/一个 triple
   `CoreJointSelectedViewManifest` 身份完整，处理矩阵无未解释非有限值；
3. WP-0072 的 `CoreProcessedFeaturePanelManifest`、
   `CoreForwardReturnLabelBatch`、选择先验和 H20/H60 选择身份均可验证；
4. 工作树从包含 WP-0072 的最新主线建立，且没有其他包修改根依赖或核心模型合同；

依赖未满足时保持 `dependency_blocked`。本包属于 D-114 持续实施授权，不再请求重复
功能授权。

## 非目标

- 不重新计算因子、处理缺失、选择特征或修改 selection manifest；
- 不实现 O0、整数手、Top5/Top10、成本后决赛、晋级参照或 CorePolicy；
- 不运行生产快照训练，不激活真实候选，不回填当前模型为历史模型；
- 不实现 Research Shadow、MiniQMT、Paper/Live、账户、StandingMandate 或订单；
- 不创建 UI，不加入预测级融合、动态周期权重、行业专家、MLP/注意力或高级优化器；
- 不训练 LightGBM；其固定预算挑战属于依赖 WP-0074A 的 WP-0073B。

## 允许文件与高争用边界

- `src/astramind_mini/strategy_research/core/modeling/**`
- `tests/unit/test_core_modeling_*.py`
- `tests/golden/test_core_modeling_calibration.py`
- `tests/fixtures/core/modeling/**`
- 本工作包及直接追踪状态

不得修改 WP-0070/0072 公共合同、三个因子包、`contracts/**`、Data、Portfolio &
Risk、Trading Execution、`composition.py`、数据库迁移、生产 `var/` 或前端。若现有
`StrategyVersion`/`PredictionBatch` 薄腰不足，先在 `core/modeling` 建立局部
manifest 并映射到公共合同；确需扩展共享合同则停止交主控串行处理。

## 唯一所有者与制品

`strategy_research.core.modeling` 拥有：

- `CoreTrainingFold` / `CoreTrainingPlan`；
- `CoreModelLineageSpec`；
- `CoreModelArtifactManifest`；
- `CoreOutOfFoldPredictionBatch`；
- `CoreCalibrationArtifact`；
- `CoreModelCandidateSet`。

所有制品使用规范 JSON 和 SHA-256 内容身份，绑定准确数据/特征快照、视图 manifest、
周期、训练截止、标签成熟截止、训练日期、列顺序、样本权重、算法参数、随机种子、
依赖版本、代码身份、模型字节哈希和父级 lineage。模型制品不得使用 pickle。

Ridge 使用项目已有的确定性安全模型制品能力。ZIP 时间戳、临时路径、线程数和进程
身份不得进入内容差异。

前向收益公式、成熟状态和标签批次由 WP-0072 的 `strategy_research.core.labels`
唯一拥有。本包只从中筛选每周最后一个共同交易日并构造模型训练计划，不得复制标签
公式、重新读取未来价格或发布第二种 `CoreLabelSpec`。

## 决策日、标签与样本

- 只使用公共 label batch 中每周最后一个沪深共同交易日 `T` 的冻结截面；
- 标签语义沿用公共
  `P_research_close(T+H) / P_research_open(T+1) - 1`，本包不得重算；
- 主目标为当日 U0 内绝对收益的升序截面百分位，平均秩并列，
  `(average_rank - 1) / (n - 1)`；`n < 2` 无效；
- H20 与 H60 分别构造标签、训练计划、模型、预测和校准，禁止共享目标或用一个多输出
  模型代替；
- 标签成熟前不得进入训练；每个训练截止按准确 H 删除末端未成熟标签；
- 每个训练日期总权重相同，日期内每只合法样本权重为 `1/n_date`；
- 不因未来无收益删除证券；特征行存在但标签不可构造时记录明确原因；
- D1/D3/D5 不进入任何训练、模板选择、候选预算或校准。

## 时间切分和季度重训

- 主训练窗为训练截止日前最近五年成熟周度样本；
- 扩展窗从首个合格日期开始，只发布平行诊断，不参与选择；
- 开发区间截至 2022-12-31；
- 2023-01-01～2025-12-31 只允许使用开发期已冻结 lineage 的逐季度真实历史模型做
  候选冻结回放；
- 每个自然季度结束后的首个合法周度决策点形成新训练计划，输入截止为该点前最后一个
  已完整冻结周；新模型从下一合法周度推理生效；
- 同一 lineage 的季度重训只产生新 `StrategyVersion`，不得重新选择特征清单、Ridge
  alpha；
- 当前模型不能回填历史；任何缺失历史模型版本使对应回放周失败关闭。

开发期超参数比较使用严格向前滚动 OOF：至少三个按时间连续的验证块，每块不少于
26 个周度决策截面；训练只在验证块之前，验证块不重叠。不能满足时该候选证据不足。
验证块边界、训练窗和所有 OOF 行进入 lineage 身份。

## B0 永久锚点

B0 只消费 F0-full 处理后主特征：

1. 按注册表方向统一正负；
2. 每个适用家族内对 observed 或已明确填补的数值等权平均；
3. 再对该证券适用家族等权平均；
4. 普通企业最多八个家族，金融企业只使用动量、反转、低波、流动性四个家族；
5. 不学习权重，不让缺失指示成为独立 alpha 权重。

B0 为 `F0-full × B0` 永久模型锚点；与 R0 的组合部分由 WP-0074A 补齐。同一输入重复
只能形成一个 B0 候选，不因季度“训练”制造伪新模型。

## Ridge 主比较

每周期最多十个配置：

1. `F0-full`、`F0-selected`；
2. `Alpha158-full`、`Alpha158-selected`；
3. `Alpha101-full`、`Alpha101-selected`；
4. 三个 selected 两两联合；
5. 一个有条件 selected 三包联合。

联合只能消费 WP-0072 为准确周期和 horizon 冻结的三个 pair/一个 triple
`CoreJointSelectedViewManifest`；本包不得重新计算跨包相关、完全链接、代表、拼接
顺序或最终列。至少一个两包联合在后续 WP-0074A 的开发期 C2 证据中相对较强单包为正，
三包联合才可标记 `combination_eligible`；C2 只改变 triple 的资格状态，不改变已经
冻结的列或身份。本包可以训练和留存 triple 研究制品，但在该门通过前不得发布为生产
候选。

Ridge 使用平方损失、截距且不惩罚截距。alpha 固定为：

`[1e-4, 1e-3, 1e-2, 1e-1, 1, 10, 100, 1000, 10000]`

开发期对每个特征配置和 alpha 形成独立滚动 OOF 候选。最终 alpha 由 WP-0074A 按 C2
证据冻结；并列依次选择低换手、少特征和 lineage ID 字典序。特征标准化已由 WP-0072
完成，训练器不得二次 scaler 或数据依赖填补。

## WP-0073B 槽位交接

本包不依据训练损失选择 LightGBM 父级。WP-0074A 必须从本包 Ridge OOF、校准、C2 和
O0 证据中分别冻结最佳 F0、Alpha158、Alpha101 和最佳已允许联合，形成最多四个
`CoreLightGBMSlotManifest`。没有合格父级 Ridge 的槽保持关闭。WP-0073B 只消费该
manifest，不能扩大槽位或回头改变 Ridge。

## 候选预算与冻结

- 每个周期先形成全部允许 Ridge OOF 证据，再由 WP-0074A 决定联合资格和 LightGBM 槽；
- 开发期先过滤数据、覆盖、标签、方向、确定性和样本充分性；
- 任何候选失败后不以亚军在 2023～2025 回放途中动态递补；
- 最终开发 Ridge 赢家的特征视图、alpha 和训练配方在回放前冻结；
- H20/H60 可以选择不同配置，不做跨周期笛卡尔组合；
- 本包不占用或判断 LightGBM 决赛预算。

## 十桶绝对收益校准

每个 `Strategy Lineage × H20/H60` 独立校准：

1. 只消费滚动 OOF 预测；
2. 每决策日将预测转为 U0 截面百分位，使用统一平均秩；
3. 按 `[0,0.1), ... [0.9,1.0]` 固定十桶，边界 1 进入第十桶；
4. 日期等权，日期内样本等权，计算各桶实际绝对 H 日收益均值；
5. 使用 PAVA 最小化加权平方误差，得到非递减十桶值；
6. 推理只映射到所在桶，边界外截到边界桶，不插值、不外推。

主窗至少需要 156 个有效周度截面，且十桶每桶至少 30 个总样本；不足时校准失败关闭。
最高桶拟合收益必须严格高于十桶拟合中位数。最高分受约束篮子的 C2 净收益正门由
WP-0074A 计算；未收到该证据前校准状态最多为 `statistically_ready`，不能称
`production_valid`。

校准器绑定 OOF 预测、绝对标签、桶边界、PAVA 权重、拟合值、训练截止和下一季度到期
时间。到期、方向失败、上游模型变化或输入不兼容时禁止新增风险，没有宽限期。

## Golden、负向证明与性能

fixture 至少包含两个周期、三个季度训练截止、五年以上周度样本、两个行业变更和：

- T+1 开盘/H 日收盘标签、并列秩、未成熟末端和未来数据追加；
- 日期等权与证券数不等的截面；
- B0 普通企业/金融企业家族差异；
- Ridge 九 alpha、截距不惩罚、full/selected 和联合列顺序；
- 十桶边界、空桶/稀疏桶、PAVA 合并、截断和到期；
- 当前模型回填历史、动态递补、三包门未过却发布等负测。
- modeling 入口收到未冻结联合、错误 horizon/周期、列顺序改变，或试图在训练器内
  重新去重时失败关闭。

小矩阵 Ridge 与 PAVA 使用手算/独立 NumPy oracle，纯数值使用
`atol=rtol=1e-12`；身份、参数、顺序、状态和哈希精确相等。

默认测试使用小型 fixture 并在 90 秒内完成。完整五年训练、全部 Ridge 候选和历史
回放使用显式慢命令，不能隐藏在默认检查中。

## 验收

1. H20/H60 的标签、训练计划、模型、预测和校准身份完全独立。
2. 标签成熟、五年滚动、季度重训和严格向前 OOF 均有未来泄漏负测。
3. B0、十个 Ridge 配置预算和九 alpha 不可配置扩张；联合列只来自 WP-0072 冻结
   manifest，训练器不能重算去重或改列。
4. 当前季度模型不能回填历史，失败候选不能动态递补，三包联合门失败关闭。
5. 十桶 PAVA 只消费 OOF，样本不足、方向失败、到期和 C2 门未完成均不能生产有效。
6. 所有制品身份绑定完整上游、环境、参数、代码和内容；篡改或错配被拒绝。
7. 导入图不包含 LightGBM、MiniQMT、账户、Portfolio & Risk、Trading Execution、
   前端或网络。

## 检查

```text
uv run pytest tests/unit/test_core_modeling_*.py \
  tests/golden/test_core_modeling_calibration.py -q
uv run pytest tests/unit/test_core_feature_processing_*.py \
  tests/unit/test_core_feature_selection_*.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/modeling \
  tests/unit/test_core_modeling_*.py tests/golden/test_core_modeling_calibration.py
uv run mypy --strict src/astramind_mini/strategy_research/core/modeling
make docs-check
git diff --check
```

慢速完整验收命令由实现包增加明确 `slow` marker，并至少覆盖两个周期和全部 Ridge
候选预算；不得触碰生产 `var/`。

## 授权与交接

本包实现和集成完成后，主控复核时间切分、日期权重、候选预算、模型确定性、安全制品、
OOF 和校准状态，再自动释放 WP-0074A。quant-kb 的约束在本包体现为：所有模型仍是待
样本外验证的假设，成本、流动性、执行和组合胜负必须留给 WP-0074A/B 的准确 C2/O0
证据，训练损失不能冒充可交易优势。

本授权不包含生产训练/激活、新 UI、生产补采、MiniQMT、Research Shadow 实际运行、
账户、StandingMandate、Paper/Live 或订单。
