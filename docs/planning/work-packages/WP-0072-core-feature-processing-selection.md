# WP-0072：核心特征处理、冻结选择与平行中性化诊断

- 版本：1.3.0
- 状态：Stage P 已实现、独立复核并集成；Stage S 已释放
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5B
- UI 提案：不适用
- 所有者：下一空闲永久工作树 / Strategy Research

## 目标

消费 WP-0071A/B/C 通过主控复核的三包原始 `CoreRawFeatureEnvelope`，建立唯一、
可复算的外层处理与折内选择链：保留规范 `full`，生成 H20/H60 各自冻结的
`selected`，完整记录三态缺失、覆盖失败、MAD 缩尾、稳健标准化、点时填补、独立状态
指示、平行行业/规模中性化诊断、RankIC、bootstrap、BH 和相关簇证据。

本包只形成特征矩阵和选择清单，不训练模型。WP-0073 只能消费本包发布且验证通过的
冻结制品，不能在训练器内再次选择、填补或改变列顺序。

## 启动门

只有下列条件全部满足才可开始实现：

1. WP-0071A、WP-0071B、WP-0071C 均已由主控独立复核并集成到同一主线；
2. 三包分别通过注册表哈希、golden、点时负测和公共 raw builder 身份验收；
3. 三包公开的规范公式/表达式和 computation manifest 足以逐项冻结 283 个 selection
   prior；任何公式缺失或定义身份不一致先返回主控，不由本包猜测；
4. 工作树已显式同步到包含三包集成提交的最新主线且保持干净。

任一因子包阻断时，本包保持 `dependency_blocked`，不得用临时公式、空列、随机数或
部分包结果代替。持续实施授权已经释放，不再请求重复功能授权。

## 非目标

- 不计算或修改 F0、Alpha158、Alpha101 公式、注册表和规范顺序；
- 不实现 B0、Ridge、LightGBM、标签训练、预测、校准、H20/H60 模型或季度编排；
- 不实现 O0、CorePolicy、组合、Research Shadow、Paper/Live 或订单；
- 不让 D1/D3/D5 参与选择、超参数、候选或晋级；
- 不建立 full 联合包，不做预测级融合、Alpha101-CN、F0-FIN 或 MKT1；
- 不修改 Data、生产 `var/`、快照指针、MiniQMT、前端或导航；
- 不把中性化残差覆盖主特征，不通过删除证券改善覆盖。

## 允许文件

- `src/astramind_mini/strategy_research/core/feature_processing/**`
- `src/astramind_mini/strategy_research/core/feature_selection/**`
- `src/astramind_mini/strategy_research/core/labels/**`
- `tests/unit/test_core_feature_processing_*.py`
- `tests/unit/test_core_feature_selection_*.py`
- `tests/golden/test_core_feature_processing_selection.py`
- `tests/fixtures/core/processing/**`
- 本工作包及其直接追踪状态

不得修改 `strategy_research/core` 现有公共合同、三个因子包、`contracts/**`、
`data/**`、`composition.py`、数据库迁移、根配置或前端。调用方分别从
`strategy_research.core.feature_processing`、
`strategy_research.core.feature_selection` 和
`strategy_research.core.labels` 导入；不修改高争用
`strategy_research/core/__init__.py`。若冻结合同无法表达必要身份，停止并把最小合同
缺口交主控单独处理。

## 唯一所有者与公共 API

Strategy Research 的三个内聚子包分别拥有：

1. `feature_processing`：三态覆盖、截面处理、填补、状态指示和中性化诊断；
2. `feature_selection`：折内 RankIC、确定性重采样、BH、相关簇和冻结清单。
3. `labels`：H20/H60 公共前向收益标签公式、成熟证据和独立标签快照；WP-0073A
   复用该公共标签，不得再定义第二套标签语义。

最小公开制品为：

- `CoreProcessingSpec`：身份固定为 `core-feature-processing-v1`；
- `CoreProcessedFeatureEnvelope`：绑定准确 raw envelope、U0、单个决策日、处理规格、
  每行处理结果、覆盖证据和内容哈希；
- `CoreProcessedFeaturePanelManifest`：按日期升序绑定
  `(decision_date, CoreInputSnapshot id/hash, raw envelope id/hash,
  processed envelope id/hash, U0 hash, control panel hash)` 日级条目；每个条目独立验证
  单一快照血缘，panel 内容哈希覆盖完整有序 tuple。跨日统计只能消费该 manifest，
  不存在或伪造一个覆盖多日的 `CoreInputSnapshot`，也不能把 T+H 数据塞回 T 日快照；
- `CoreForwardReturnLabelSpec` / `CoreForwardReturnLabelBatch`：绑定 H20/H60、
  T+1 开盘、T+H 收盘、标签数据快照、可用截止、成熟状态、绝对收益和截面百分位；
- `CoreSelectionPriorManifest`：在打开 RankIC 前冻结每个定义的
  `feature_id@version`、预期方向、经济机制、规范表达式和复杂度；
- `CoreSelectionFold` / `CoreSelectionPlan`：只拥有特征选择的开发折和身份，不代替
  WP-0073A 的模型训练计划；
- `CoreSelectionSpec`：身份固定为 `core-feature-selection-v1`；
- `CoreFeatureSelectionManifest`：绑定包、`H20` 或 `H60`、训练折、标签身份、方向登记、
  选择证据、选中列有序清单和内容哈希；
- `CoreFeatureViewManifest`：声明 `full` 或准确 `selected` 视图、规范列顺序、数值列、
  指示列、实际 `model_input_dimension` 和上游身份。
- `CoreJointSelectedViewManifest`：按 H20/H60 分别冻结三个 selected 两两联合和一个
  selected 三包联合的准确父级、跨包相关、完全链接簇、代表选择、最终列顺序和内容
  哈希；它拥有跨包去重，模型训练器只能消费，不能重新选择或改列。

以上制品全部使用规范 JSON 序列化和 SHA-256 内容身份。重复运行必须幂等；上游 raw
身份、U0、决策日、处理规格、标签、折边界、方向、种子、选择结果或列顺序变化必须
形成新身份。`selected` 不得沿用 `full` 的身份。

## 输入和点时边界

- 每个日级处理请求只消费一个不可变 `CoreInputSnapshot` 血缘，不混合数据版本；
- 每个处理 envelope 只对应一个决策日；跨日期处理和选择由
  `CoreProcessedFeaturePanelManifest` 以上述日级 tuple 有序聚合；每个条目分别校验
  decision date、快照、raw、processed、U0 和控制面身份，不能伪造一个
  “多日 CoreInputSnapshot”或用一个日期的快照替代其他日期；
- 处理截面必须是该决策日完整 U0 研究成员，不因状态或值缺失删除证券；
- 只处理三包公共 raw builder 已验证的有限 `observed` 数值和显式非观测状态；
- 标签由本包 `labels` 子包按 WP-0070 共同交易日历和 REQ-2026-0007 第 4 节构造，
  入场为 T+1 连续研究开盘价，终点为 T+H 连续研究收盘价；标签批次独立绑定实际
  T+H 数据快照及可用截止，标签成熟前不可进入选择；
- 训练折必须删除末端尚未成熟的 H60 标签，不加入未登记的对称 embargo；
- 行业和流通市值控制只使用决策时点可知记录，不能回填当前行业或未来市值；
- 当前会话行情、形成中分钟、未封存 Tick、X0 和执行诊断不得进入本包。

### U0 与控制面板

`CoreProcessingControlPanel` 按决策日、证券冻结完整 `CoreUniverseDecision`、
点时 SW2021 L1、流通市值、各观察的 `available_at`、来源数据集身份和内容哈希。
证券集合必须与当日 U0 研究成员逐一相等，缺行、多行、额外行、U0 哈希不符或控制记录
晚于决策截止均失败关闭。行业/规模控制缺失只使相应填补回退或中性化诊断不可用，
不能删除证券。

每个 `CoreForwardReturnLabelBatch` 还必须逐 T 绑定当日完整
`CoreUniverseDecision` 有序审计行集和 `universe_content_hash`。batch 可以保留
`research_member=false` 的非成员审计行，但百分位分母严格限于当日
`research_member=true` 且具有合法、成熟绝对收益的行。制品同时保存
`n_universe_rows`、`n_research_members`、`n_valid_returns` 和
`label_coverage=n_valid_returns/n_research_members`；百分位公式的 `n` 等于
`n_valid_returns`。其他行 percentile 为空并保留原因，`n < 2` 时整个标签截面无效。
每个预期证券必须有合法标签或明确
`not_matured / entry_missing / horizon_close_missing / not_research_member` 原因。
选择入口逐日只在 `research_member=true` 的有序子集上验证 label U0、processed
panel U0 和控制面 U0 的证券与 hash 完全相等；非成员审计行不参与 rank、模型或三方
相等比较，不能只比较日期或证券交集。

## 三态覆盖门

对每个包、每个因子、每个训练折先确定公式适用集合：

- `observed`：进入覆盖分子和分母；
- `missing`：进入适用分母，不进入分子；
- `not_applicable`：不进入适用分母，但必须保留在模型行和独立指示列。

逐训练日期计算：

`coverage_d = observed_count_d / applicable_count_d`

当 `applicable_count_d = 0` 时该日不构成合格覆盖日，并记录
`no_applicable_members`。因子只有在至少 90% 的有适用成员训练日期上满足
`coverage_d >= 0.80` 才通过：

`passing_date_ratio = count(coverage_d >= 0.80) / count(applicable_count_d > 0)`

无任何有适用成员日期或 `passing_date_ratio < 0.90` 时，整个因子在该折失败关闭，
不能进入 `selected`。覆盖统计必须保存日期数、逐日计数、比率和稳定原因码。
原始 envelope 的 `observed_coverage_ratio=observed/row_count` 只用于原始制品审计，
因为其分母含 N/A，不能复用为本门槛；本包必须发布独立的 applicable coverage
evidence。

## 统一截面处理

处理次序固定为“状态规范化 → observed 截面缩尾/标准化 → 状态感知填补 → 指示列 →
平行诊断”，每个决策日、每个因子独立执行。

### observed 值

对当日 U0 中合法、有限的 `observed` 原始值集合：

1. `m = median(x)`；
2. `s = 1.4826 * median(abs(x - m))`；
3. `winsorized = clip(x, m - 5*s, m + 5*s)`；
4. `z = (winsorized - m) / s`。

公共 raw envelope 已拒绝非有限 observed；“非有限转 missing”只属于纯规范化内核的
防御性单测，受保护入口遇到该状态必须先拒绝被篡改的 raw envelope，不能绕过公共
合同后发布 processed 制品。若没有 observed 值，截面处理失败关闭。若 `s = 0`，所有合法
observed 值的 `winsorized` 保留原值、`z = 0`，并记录 `zero_scale`；不得加入 epsilon。
原始值、`m`、`s`、上下界、缩尾值和 z 值都必须可重建。

### 状态感知填补

填补统计量只使用当日该因子的合法 observed 主 z 值：

- `missing`：先取该证券点时 SW2021 L1 行业内 observed 中位数；行业至少 10 个
  observed 成员才可用，否则取当日 U0 observed 中位数；
- `not_applicable`：保持状态独立，数值占位只取当日 U0 observed 中位数；
- 当日无 U0 observed 中位数时该因子截面失败关闭，不用 0 或跨日数据填充；
- 行业身份缺失或行业 observed 少于 10 时，只允许明确回退 U0 中位数。

每个规范因子输出一个数值列、一个 `is_missing` 和一个 `is_not_applicable` 指示列。
observed 行两个指示均为 0；非观测行只有与其准确状态对应的指示为 1。填补来源固定为
`none / sw_l1_median / u0_median`，不得把占位数值改写成 observed。

### 平行中性化诊断

对当日 observed 主 z 值做带截距 OLS：

`z = intercept + beta_size * log(float_market_cap) + SW_L1_one_hot + residual`

行业 one-hot 使用确定性字典序，并删除字典序第一层作为基准，防止虚拟变量陷阱。
只有所有控制点时可用、`n >= 5 * p` 且设计矩阵满列秩时才发布残差；其中 `p` 是实际
设计矩阵列数，包含截距、规模和 `k-1` 个行业列。否则诊断状态分别记录
`controls_missing / insufficient_sample / rank_deficient`。

残差只属于诊断制品，不进入主数值列、选择、模型输入或联合包，也不覆盖原始或处理后
特征。OLS 数值允许 `atol=rtol=1e-9`，状态、样本数、列数和原因码必须精确相等。

## full 与 selected

- `full` 永久保持包的规范公式顺序；处理失败或覆盖失败的因子仍存在于 full manifest，
  并保存状态，不能悄悄删列；任一父因子在准确训练折未通过覆盖门时，包含它的
  `full` model view/candidate 必须标记 `blocked/coverage_gate_failed`，不能让低覆盖
  因子穿透到 B0 或 Ridge；
- `selected` 只能在准确训练折内生成，列顺序沿用 full 的规范顺序，不按统计量重排；
- H20 与 H60 分别选择并允许不同；二者不得强制取交集；
- 2023～2025 回放只能使用 2022-12-31 前已冻结的选择清单；
- 本包为每个周期发布三个 selected 两两联合和一个 selected 三包联合
  `CoreJointSelectedViewManifest`，先按 F0、Alpha158、Alpha101 包顺序和各包规范
  列顺序拼接，再按本包冻结的跨包完全链接与代表规则去重；不允许 full 联合。
  WP-0073A 只消费该准确 manifest，不能重新计算相关、去重或改变列；
- 每个非 observed 指示列跟随其父因子；父因子未选中时对应指示列也不进入模型；
- `model_input_dimension` 等于选中数值列加其准确两类状态指示列的实际总数，不能仍称
  24、158 或 101 维。
- 每个父因子的视图列固定按
  `<feature_id>__value, <feature_id>__is_missing, <feature_id>__is_not_applicable`
  排列，父因子之间沿规范公式顺序；列名、父级映射和顺序都进入内容身份。
- full manifest 永久保留无 observed 截面的定义，但其模型视图标记
  `blocked/no_observed_cross_section`；不得删列、填 0 或以其他日期统计量解锁。
  因而 Alpha101-full 等候选可以合法处于 blocked，WP-0073A 不得绕过。

阻断粒度固定如下：单因子单日无 observed 只阻断该日整个模型 view，不删除证券；
训练计划可带稳定原因码排除该完整日期，但不能重算覆盖或选择证据，且排除日期和原因
进入模型 lineage。某因子在整个 fold 无 observed、未通过折内 coverage 门、排除后
达不到下游最小样本，或当前推理日任一必需父因子阻断时，整个对应 full 候选阻断；
selected 只允许排除 coverage fail 或 selection-ineligible 的父因子，并必须引用准确
选择证据。不得临时删除其他父因子、以其他日期填充或只删除缺失证券来挽救候选。

联合 manifest 对各单包已经冻结的 selected 父因子使用本节同一逐日相关样本、未知距离、
`abs(median_corr) >= 0.85`、完全链接和代表 tie-break；相关与代表证据必须写入联合
manifest，而不是只保存最终列。每个 H20/H60 各发布 F0+Alpha158、F0+Alpha101、
Alpha158+Alpha101 三个 pair 和一个 triple，共八个身份独立制品。后续 C2 只决定
triple 是否具备生产候选资格，不得回写、重算或改变该 triple 的冻结列。

## H20/H60 折内选择算法

### 冻结先验与样本日历

- H20/H60 特征选择使用每日完成日截面；模型训练和生产证据仍由 WP-0073A 使用每周
  最后一个共同交易日。每日选择样本不得伪装成周度模型证据；
- `CoreSelectionPriorManifest` 对 283 个规范定义逐项冻结方向 `+1/-1`、非空经济
  机制 ID、简体中文机制摘要、规范表达式和复杂度，不允许 `unknown`、开发后改符号
  或遗漏定义；
- 复杂度固定为规范表达式词法序列中函数名、算术/比较/逻辑运算符、滚动/滞后算子
  的 token 数；变量、括号和数值常量不计。tokenizer 版本和表达式哈希进入 manifest；
- 若包公式、计算 manifest、方向、机制、适用范围、tokenizer 或复杂度变化，必须形成
  新先验身份和新的选择 lineage；
- 每个选择折由有序每日决策日、标签成熟截止、panel manifest、label batch 和先验
  manifest 唯一标识。开发折至少拆成三个连续子折，每个子折至少 60 个有效每日
  RankIC；不足时方向一致性为失败，不用较短区间替代。

WP-0072 分两个提交阶段：Stage P 只能阅读规范公式和公开语义，创建
`feature_selection/core_selection_priors_v1.json`，由主控独立复核 283 项完整性、
方向和机制摘要并把内容哈希写入本包实施结果；在该提交冻结前禁止运行或查看任何
RankIC、标签收益、2023～2025 回放或选择输出。Stage S 只能消费已冻结 prior，不得
在统计开发中改写。Stage P/S 均属于现有持续实施授权，不是新的用户授权门。

每个包、每个生产周期独立执行：

1. 在每个有效决策日计算因子主 z 值与成熟截面百分位标签的 Spearman RankIC；
   截面不足 2 个成对 observed 样本时该日无效；
2. RankIC 乘因子注册表预登记方向，得到序列并计算 `mu`；
3. 对 `IC - mu` 使用 20 个决策截面的圆形移动区块 bootstrap，固定 10,000 次；
4. 单侧 `p = (1 + count(centered_bootstrap_mean >= mu)) / 10001`；
5. 因子只有在 coverage 合格、三个连续子折各至少 60 个有效每日 RankIC，且能形成
   有限 p 值时才是 `selection_eligible`；任一条件不足以稳定原因码持久化且不得入选。
   在同一包、同一周期、同一折的准确有序 `selection_eligible` 集合上执行
   Benjamini–Hochberg，`m` 就是该集合大小；保存被排除定义及原因、准确检验族、原始
   p、排序、阈值和通过状态，不能把无 p 项计入 `m` 或当作 p=1；
6. 对 BH 通过项计算逐日截面 Spearman 因子相关，再取跨日中位数；
7. `abs(median_corr) >= 0.85` 进入同一候选簇，使用完全链接；不得用单链接造成链式
   合并；
8. 每簇只保留一个代表，依次比较：预登记方向跨折一致、注册表公式复杂度更低、覆盖
   更高、特征换手更低、RankIC 稳定性更高、注册 ID 字典序更前。

因子相关只使用两个父因子在当日都为原始 `observed` 的处理后主 z 值，平均秩处理
并列；配对证券少于 5 的日期无效，每对因子至少需要 60 个有效相关日，否则距离为
`correlation_evidence_insufficient`，不得把未知距离当作 0、1 或可合并。特征换手也
只使用相邻两日都为原始 `observed`、且属于两日 U0 交集的证券。先在每一日完整
original-observed U0 截面上按平均秩
`(average_rank - 1) / (n_day - 1)` 独立计算百分位，`n_day < 2` 时该日无效；再取
相邻日 observed 交集计算绝对变化均值。证据保存两日各自 `n_day` 和交集 `n_common`；
至少 5 只共同证券和 60 个有效日期转移，否则为 `not_comparable`。不得先缩成两日
交集后重排百分位，填补值和 N/A 占位也不得进入相关或换手。

BH 将候选按 `(p_value, feature_id@version)` 升序排列，取最大
`k: p_k <= (k/m)*0.10`，前 k 项通过；p 值相同也不得依赖输入顺序。相关距离固定为
`1 - abs(median_daily_spearman)`；完全链接从单元素簇开始，只合并最大两两距离
`<= 0.15` 的簇；任一两两距离未知则该合并不合法。候选合并并列时按两个有序成员
ID 元组的字典序决定。

三个连续子折各自至少 60 个有效每日 RankIC 是前述 `selection_eligible` 的样本充分性
门。样本充分后，只有三个子折的有符号平均 RankIC 均严格大于 0 才记录
`direction_consistent=true`，否则为 `false`；该布尔只作为第 8 步簇内代表的第一
tie-break，`false` 的孤立簇不因此被淘汰，也不改变 BH 的 `m`。任一子折不足仍是
`selection_ineligible`。覆盖比较量为折内
合格日期 `coverage_d` 的算术均值；特征换手为相邻有效日期、共同证券上截面百分位
绝对变化均值的时间中位数，越低越优；稳定性为
`1 / (1 + MAD(signed_daily_RankIC))`，越高越优。任一比较量不可构造时使用明确
`not_comparable` 并排在可比较候选之后，不用 0 冒充。

所有比较量必须是有限标量或明确 `not_comparable` 并持久化。完全相同才进入下一
tie-break。
预登记方向和公式复杂度来自冻结注册表，不能根据开发期表现回写。D1/D3/D5 可由后续
诊断调用同一统计原语，但其结果不得写入 H20/H60 selection manifest。

### 确定性种子

种子输入使用 UTF-8 文本：

`feature_id + "@" + definition_version + "|" + horizon + "|" + fold_identity`

计算 SHA-256，取 digest 前 8 字节按 big-endian 解释为无符号 64 位整数。区块起点由
该种子的 SplitMix64-v1 流生成：每次先令
`state=(state+0x9E3779B97F4A7C15) mod 2^64; z=state`，
`z=((z xor (z>>30))*0xBF58476D1CE4E5B9) mod 2^64`，
`z=((z xor (z>>27))*0x94D049BB133111EB) mod 2^64`，
`output=z xor (z>>31)`；起点为输出 `mod n`，按该精确映射有放回取样，不使用拒绝
采样或浮点均匀分布。每次 replicate 依次生成
`ceil(n/20)` 个起点，每个展开 `(start+j) mod n, j=0..19`，拼接后只保留前 n 项；
严格按 replicate 0..9999 顺序计算。必须提交至少三个
`seed → 前十起点 → 首个重采样索引` golden vector。训练行顺序、证券顺序、行业顺序和并列秩规则必须固定；
禁止使用进程随机 hash。

## Golden 与负向证明

golden fixture 至少包含：

- 三个包、260 个共同交易日、至少 24 只证券、三个 SW L1 行业，以便同时覆盖
  `n >= 5*p` 的成功 OLS 和样本不足分支；
- observed/missing/not_applicable、非有限输入、零 MAD、行业不足 10 个 observed、
  无 U0 observed、控制缺失、样本不足和秩亏；
- H20/H60 不同有效因子、BH 临界通过/失败、正负相关和完全链接反链式案例；
- 两个训练折及一个 2023～2025 冻结回放身份；
- 追加未来行情、标签、行业或市值后，历史截止前制品和选择身份不变。
- 标签未成熟、标签快照晚于选择截止、U0/控制面板缺行/多行、旧 raw coverage 被误用、
  非成员审计行进入 rank、coverage fail 穿透 full、无 p 项污染 BH 的 `m`、先缩成交集
  再算换手百分位、把 `direction_consistent=false` 错当硬淘汰或改变 BH `m`、训练器
  重算联合去重、全 N/A full 视图、D1/D3/D5 注入及旧先验 hash 攻击均有失败关闭反例。

处理 oracle 使用手算小截面；Spearman、OLS、BH 和 bootstrap 至少各有独立参考实现，
不得调用生产入口生成期望值。处理数值使用 `atol=rtol=1e-12`，OLS 和相关归约使用
`1e-9`；p 值、种子、ID、顺序、状态、原因码和哈希精确相等。

## 验收

1. 三包相同状态和数值输入使用同一处理实现，不存在包内私有填补或标准化。
2. 覆盖门精确执行“90% 日期达到 80% observed”，N/A 不污染适用分母。
3. MAD、零尺度、行业/U0 填补、双状态指示和无可填补截面均通过正负测试。
4. 中性化只形成平行诊断，控制缺失、样本不足或秩亏时失败关闭且不影响主特征。
5. full 保持规范顺序；selected 只读训练折，H20/H60 独立冻结，未来数据不改变旧清单。
6. bootstrap 10,000 次、BH 10%、相关阈值 0.85、完全链接和 tie-break 可重复且有反例。
7. D1/D3/D5 无法影响 H20/H60 manifest；联合 full 和未冻结 selected 被拒绝。
8. 同一输入重复运行身份一致；任何语义输入变化重标识；默认检查在 90 秒内。
9. 导入图不包含 Data 内部模块、MiniQMT、Portfolio & Risk、Trading Execution、
   LightGBM、前端或网络。
10. 单日 processed envelope 与绑定完整日级 tuple 的多日 panel 身份分离；标签使用
    独立成熟数据快照；research-member U0/控制面板精确行集、每日选择日历、先验
    方向/机制/复杂度、BH 准确检验族、linkage 并列、跨包联合 manifest 和固定视图
    列顺序均有篡改负测。

## 检查

```text
uv run pytest tests/unit/test_core_feature_processing_*.py \
  tests/unit/test_core_feature_selection_*.py \
  tests/unit/test_core_labels_*.py \
  tests/golden/test_core_feature_processing_selection.py -q
uv run pytest tests/unit/test_core_universe.py tests/unit/test_core_data_semantics.py \
  tests/unit/test_core_feature_identity.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/feature_processing \
  src/astramind_mini/strategy_research/core/feature_selection \
  src/astramind_mini/strategy_research/core/labels \
  tests/unit/test_core_feature_processing_*.py tests/unit/test_core_feature_selection_*.py \
  tests/unit/test_core_labels_*.py tests/golden/test_core_feature_processing_selection.py
uv run mypy --strict src/astramind_mini/strategy_research/core/feature_processing \
  src/astramind_mini/strategy_research/core/feature_selection \
  src/astramind_mini/strategy_research/core/labels
make docs-check
git diff --check
```

## 授权与交接

本包属于 D-114 的周度核心首期离线持续实施授权，不需要再次请求功能实施许可。实现
和集成完成后，主控复核处理公式、状态转换、未来泄漏、选择统计、完全链接、冻结身份
及运行时导入图；通过后可自动释放 WP-0073。

本授权仍不包含新 UI、生产数据补采、MiniQMT 新调用、账户、StandingMandate、
Research Shadow 实际运行、Paper/Live 或订单。上述边界不能借本包扩大。

## Stage P 实施结果

- 已从主线 `27fb4113e7a7c7f92a94a5c90c5815852bd5bbe8` 集成的三个公开公式注册表机械提取
  24/158/101 项规范顺序、定义版本、表达式和 registry/computation manifest 身份；
- `core_selection_priors_v1.json` 共冻结 283 项事前方向和简体中文经济机制，内容哈希为
  `sha256:818554838477dd7ad9d3f4fc9490551cae0a78d69a315eb781fa62ed2a630952`；
- 复杂度使用 `core-selection-complexity-tokenizer-v1`，规则哈希为
  `sha256:7e2fa6eed8a0b668393f5b40ba65360b83d20f47742fd430bdbe7efa8b7aa3e4`；
- Alpha101 四个申万三级公式保留 `+1` 先验并显式登记当前 capability
  `unavailable`，不改变公式身份或方向；
- 本阶段未实现处理、标签、选择统计或运行时代码，未读取任何开发统计、回放、选择或
  模型结果；Stage S 只能消费已冻结内容哈希，任何先验变化必须新建版本与 lineage。
- 独立复核从隔离提交 `e857d0e5e21302e634b6cc37222948e511690126` 机械重建 F0 24、
  Alpha158 158、Alpha101 101，共 283 项；ID、顺序、表达式、适用性、方向、机制、
  L3 capability、表达式哈希和复杂度逐项一致；
- 聚焦测试、三包联合回归、Ruff、变更范围 strict mypy、仓库检查、架构检查和 diff
  检查均通过；Stage P 已作为主线提交 `74b4b08` 集成，Stage S 必须从包含该提交的
  最新主线新建单写者分支。

## Stage S 实施结果

- 已实现 D1/D3/D5 诊断标签原语和 H20/H60 可选择标签；入口固定使用 T+1 连续研究
  开盘价、T+H 连续研究收盘价、成熟标签独立快照和逐日 U0，非成员只留审计行，不进入
  百分位；
- 已实现三包共用的三态外层处理、80%/90% 覆盖门、5 MAD 缩尾、稳健 z、行业恰满
  10 个 observed 后的状态感知填补，以及仅作平行证据的行业/规模 OLS；非有限输入、
  无 observed、控制缺失、样本不足和秩亏均失败关闭；
- 已冻结单日 processed envelope、完整逐日 lineage 的 panel、H20/H60 独立 selection
  manifest、单包 full/selected view，以及每周期三个 selected pair 和一个 selected
  triple；selection 同时保存准确日 envelope/U0 父级，未来尾部或替换父级不能进入旧
  折身份；
- selection manifest 进一步绑定准确 `CoreSelectionPlan` id/hash；唯一
  parent-aware 入口从真实 panel、按序 processed envelopes、H20/H60 label batches、
  fold/plan/spec 和完整 Stage P prior 调用生产 `select_core_features` 重建。所有接收
  candidate manifest 的 single view、single projection、joint builder/view 与 joint
  projection 公共边界都执行该重建和逐字段比较；不签发或信任任何可由外部传入的
  Python receipt。性能仅通过完整内容指纹后的确定性 selector 缓存和一次性证据索引
  优化，不改变 10,000 次 bootstrap；
- 已实现折内每日 RankIC、三个连续 60 日子折门、SplitMix64-v1 圆形区块 bootstrap、
  BH 10%、逐日相关时间中位数、完全链接和代表选择；D1/D3/D5、旧 Stage P hash、
  未冻结父级、相关证据不足和跨包 U0 不一致均有失败关闭检查；
- 单包和联合 view 可直接按 manifest 物化已填补、有限、行列顺序固定的实际矩阵；
  blocked/空 selected 仍发布准确身份，但不能投影模型矩阵，下游不得重做填补、选择或
  列排序；
- 受控 oracle 已升级为三个包、260 个固定真实沪深共同交易日、24 只证券和三个行业
  的实际 18,720 条输入及 18,720 条处理输出；该处理 fixture 与 horizon 无关，同一
  fold 的 H20/H60 共享完全相同的 processed panel/envelope 身份，差异只来自 label
  batch 和选择证据。另以 2022 年 242 个真实共同交易日冻结两个 180 日 H20/H60
  训练父级，并把 2023-01-01～2025-12-31 的 727 个真实共同交易日全序列、日历源
  哈希和两个 2022-12-31 前选择父级绑定为独立 frozen replay identity。fixture
  规范内容哈希为
  `sha256:5288d5d4bce3e368d5925e8f1721313b69356292663d453d1cb15e10296b4721`，
  输入、处理输出和选择回放哈希分别为
  `sha256:52b49d96423a5c5d7c1cb874968e220c5ab8db7524935a8e40f98632c6c1f4f2`、
  `sha256:06adf9486beff0ae15c109e98a291bc737f03501d0257d121a0dba1669e8a47c` 和
  `sha256:7671ae4fddb257d48e495890f4b51b7976ee4cc8c5e806696be3169dd2eb1830`；
  2023～2025 frozen replay 哈希为
  `sha256:682355c785842075e97e64812f577a557ee8dcfae5123c9f9a99053ca938e053`；
- oracle 由 `generate_stage_s_oracle.py` v4.0.0、独立证据生成器和独立决策重演器仅用
  标准库及冻结输入生成，三个文件 SHA-256 分别为
  `54b7c8d3bca5a37c5ba118902efdea4a3a4c7c2997bd87cb1c25861bdd3d4c76`、
  `aa1f589860a315777c4406ccbe5480d4a713523892cf6f1d0446f6177519005d` 和
  `17cb4175b9a5e61c90c687429436252e2668d0ef6583bf5f56513b9aa237b285`，
  运行 `uv run python tests/fixtures/core/processing/generate_stage_s_oracle.py` 可确定性
  重建；测试独立重算生成器、输入、输出、回放和 fixture 哈希。独立决策重演器从
  p/evidence 重算 BH、逐日 Spearman、完全链接、代表、换手和 selected，全部 p 改为
  `1.0` 时必须空选；另用手算 MAD/平均秩/BH/完全链接及独立 10,000 次 bootstrap
  校验生产原语，未调用生产 evaluator 生成期望值；
- 三个生成文件分别按处理、选择证据和选择决策的自然职责拆分；497/310/229 行生成器
  和约 4.5 MB fixture 属于单用途、可审计生成过程与高内聚逐行 oracle 数据，按仓库
  规则作生成/fixture 豁免；生产源码均不超过 350 行，新增函数均不超过 80 行；
- selection manifest 会从逐日证据重算固定 Stage P/tokenizer 身份、coverage 日历与
  阈值、BH 检验族、完全链接簇、代表和 selected；单包及联合 view/projector 必须消费
  准确 panel、processed envelope、selection 和单包 view 父对象，替换内容后重算全部
  ID/hash 仍失败关闭。换手证据逐相邻日保存两日 `n_day`、`n_common`、比率及有效/失效
  原因；
- 真实父级反例覆盖 bootstrap p 从 `1/10001` 改为 `0.01`、Spearman 从真实值改为
  `0.0` 后拆簇、替换 representative/selected、逐 transition turnover 改为
  `0.5/0.9` 并同步汇总；即使重算 selection/view/joint 全部 hash/ID，也会在首个
  接受 selection 的公共入口失败关闭。六证券反链式样例在距离阈值 `0.15` 下固定为
  `(A,B)+(C)`；
- golden 明确证明一个行业拥有至少 10 个 observed 同业时 missing 使用
  `sw_l1_median`，且该值与 U0 median 不同；N/A 始终只使用 U0 占位。生产回放同时
  冻结稳定 turnover=0、非零有效 transition、两类无效 transition、missing/N/A、
  selected/rejected、BH pass/fail、相关簇及代表，并证明对抗性 imputed model value
  不进入 observed-only RankIC；
- 旧 receipt 的子类覆盖、合法 guard 复制和 `object.__new__`/`object.__setattr__`
  三类伪造均不能通过 single view/projector 或 joint builder/projector；正常候选
  manifest 也只有经完整真实父级重建相等后才能继续；
- 最终 affected-scope 共 54 项处理、选择、标签与 golden 测试；首次冷环境基线为
  80.78 秒，完整信任边界与安全内容缓存就绪后的连续暖运行分别为 79.85/79.28 秒，
  保留 10,000 次 bootstrap 且满足本工作包 `<=80s` 暖运行目标；
- Stage P 的 283 项先验文件保持零差异，冻结内容哈希继续为
  `sha256:818554838477dd7ad9d3f4fc9490551cae0a78d69a315eb781fa62ed2a630952`；
  本阶段未读取生产 `var/`、历史胜负或模型结果，也未触碰 MiniQMT、账户、Paper、
  Live、组合或订单。
