# WP-0071C：论文 Formulaic Alpha101 v3 保真计算包

- 版本：1.3.0
- 状态：已完成；等待主控独立复核与集成
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5A
- UI 提案：不适用
- 所有者：Worker C / Strategy Research
- 依赖：WP-0070 已完成并集成

## 目标

建立 `formulaic-alpha101-v3` 的本地、可审计、失败关闭计算包：

1. 按 Kakushadze《101 Formulaic Alphas》arXiv:1601.00991v3 固化
   Alpha#001～Alpha#101 的连续编号、原始公式、常数、窗口、输入依赖和规范顺序；
2. 冻结本地算子语义 `alpha101-operator-semantics-v1`，消除论文未明确规定但实现必须
   唯一决定的 rank、滚动窗口、并列、缺失和数值域行为；
3. 消费 WP-0070 的 `U0-v1`、`core-data-semantics-v1`、`CoreInputSnapshot` 和公共
   原始特征输出合同，形成 101 维、逐证券逐日的三态原始公式结果；
4. 以手算算子、260 日 full、65 日 edge 和点时行业 fixture 证明公式保真、点时正确和
   A 股边界失败关闭。

本包只负责 F2 原始公式值。它不得把论文公式改写成 A 股近似版，也不得根据回测表现
调整公式、常数、窗口、适用范围或缺失规则。

## 权威来源与不可变身份

唯一公式来源：

- Zura Kakushadze, *101 Formulaic Alphas*；
- arXiv 身份：`1601.00991v3`；
- v3 日期：2016-03-18；
- 论文页：[arXiv:1601.00991v3](https://arxiv.org/abs/1601.00991v3)；
- PDF：[1601.00991v3 PDF](https://arxiv.org/pdf/1601.00991v3)；
- 本工作包审计 PDF 字节数：`244416`；
- 本工作包审计 PDF SHA-256：
  `1f9c21afe32dcb3ee77b31548acdaea00451fbfa1c0ee10c907867bcc736fce9`。

本地包身份继续使用 WP-0070 已冻结的：

```text
package_id = formulaic-alpha101-v3
canonical_dimension = 101
authoritative_source = arxiv-1601.00991v3
data_semantics_version = core-data-semantics-v1
universe_version = U0-v1
operator_semantics_version = alpha101-operator-semantics-v1
```

注册表必须证明论文 Alpha#001～Alpha#101 连续、无缺号、无重复，并以
`alpha101_001`～`alpha101_101` 作为本地稳定 `feature_definition_id`。原始公式文本、
原始数字字面量、规范 AST、输入依赖、行业层级、取整后窗口、最大历史需求和论文页码
共同进入注册表内容身份。不得只保存计算后的窗口或手写函数名而丢失论文原文身份。
首版本 101 个定义均使用本地 `feature_definition_version = 1.0.0`；该版本的定义清单
必须绑定 PDF hash、公式注册表 hash 和 `alpha101-operator-semantics-v1`。以后任何
公式转录、输入映射或算子解释变化都必须提升定义版本并形成新证据身份。

WP-0070 公共注册表按 `alpha101_001`～`alpha101_101` 和统一
`feature_definition_version=1.0.0` 固定为
`sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5`，
必须与包规格的 `required_definition_registry_hash` 一致。公共哈希约束名称、顺序和
定义版本；论文原始公式、AST 和算子语义仍由本包更严格的注册表内容哈希与 golden
共同约束。

第三方实现不是规范来源。运行时和测试时均不得访问 GitHub、其他代码仓库或在线公式
服务；实现所需公式、注册表和 golden 必须全部随本地包版本化。

## 范围与允许文件

实施只允许修改或新增：

- `src/astramind_mini/strategy_research/core/formulaic_alpha101/**`
- `tests/unit/test_formulaic_alpha101_registry.py`
- `tests/unit/test_formulaic_alpha101_operators.py`
- `tests/unit/test_formulaic_alpha101_evaluator.py`
- `tests/fixtures/core/formulaic_alpha101/**`
- `docs/planning/work-packages/WP-0071C-formulaic-alpha101-v3-package.md`

建议包内按职责拆分：

```text
formulaic_alpha101/
  __init__.py
  registry.py
  formulae_v3.json
  syntax.py
  scalar_operators.py
  cross_section.py
  time_series.py
  industry.py
  inputs.py
  evaluator.py
  reasons.py
```

`formulae_v3.json` 是一份内聚的 101 公式注册制品，可因规范数据性质豁免普通代码行数
目标；解析、算子和执行代码仍遵守模块与函数预算。不得把 Alpha101 专属语义放进
`utils.py`、共享 contracts 或第二套特征注册表。

## 受影响合同与保护边界

本包只消费，不修改：

- `FORMULAIC_ALPHA101` / `CoreFeaturePackageSpec`
- `CoreInputSnapshot`
- `CoreUniverseDecision`
- `IndustryMembershipObservation`
- `CoreRawFeatureRowDraft`
- `prepare_core_raw_feature_batch` / `finalize_core_raw_feature_envelope`

输出必须复用 WP-0070 的两阶段原始特征 builder，并绑定准确
`core_input_snapshot_id`、共同交易日历、U0 内容身份、公式注册表身份和算子语义身份。
公式注册表与算子语义通过每行 `feature_definition_version` 所引用的不可变定义清单
进入身份，不能另加未受公共 builder 哈希保护的旁路元数据。
不得复制或重写 U0、数据截止、三态、原始特征 envelope 或 `FeatureSnapshot` 身份逻辑。

若实现证明必须修改 WP-0070 公共合同、`core/__init__.py`、共享 contracts、Data
上下文、composition 或数据库迁移，停止并返回主控，不在本工作包扩大范围。

## 公式审计约束

### 101 个公式

- 注册顺序严格为 Alpha#001～Alpha#101。
- 论文中的大小写不影响解析，但原始文本仍保存以供审计。
- 所有常数和小数窗口保存原始十进制 token；求值前才按算子规则转换。
- 小数时间窗口集中在 Alpha#058、#059、#061～#082、#084～#099；不得四舍五入。
- `adv{d}` 只允许论文出现的
  `{5,10,15,20,30,40,50,60,81,120,150,180}`。
- 完整输入最长历史需求至少覆盖 252 个共同交易日；65 日 fixture 不能冒充 101 式
  全窗口数值证明。

必须保留论文 AST，即使表达式可代数化简。特别包括：

- Alpha#019 的重复价格差；
- Alpha#029 的 `close - 1`；
- Alpha#059、#066、#082、#089 的同变量加权项；
- Alpha#062 的重复 `rank(open)`；
- Alpha#077 的可抵消项；
- Alpha#100 的两次相同 subindustry neutralize。

关键易误抄项必须有独立注册表断言：

- Alpha#053 的分母是 `close - low`；
- Alpha#046、#049、#051 的阈值分别为 `0.25`、`-0.1`、`-0.05`；
- Alpha#101 分母包含论文原始常数 `.001`。

论文将 Alpha#042、#048、#053、#054 描述为 delay-0。AstraMind 仍只在 T 日完整日线
提交后计算，并按 REQ-2026-0007 的 T+1 研究执行口径消费；不得伪造 T 日收盘成交。

### 输入全集

规范输入只包括：

```text
returns
open, high, low, close
volume
vwap
cap
adv5, adv10, adv15, adv20, adv30, adv40, adv50, adv60,
adv81, adv120, adv150, adv180
point-in-time IndClass
```

按 `core-data-semantics-v1` 固定映射：

- `open/high/low/close` 使用连续 `research_*_index`；
- `returns = research_close_index(t) / research_close_index(t-1) - 1`，使用简单
  close-to-close 收益，不使用对数收益；
- `volume` 使用原始点时成交股数，单位为股，不使用“手”；
- `vwap = raw_amount_cny / raw_volume_shares`，再乘
  `research_close_index / raw_close_cny` 缩放到同一连续研究价格指数；
- `cap` 固定为点时总市值，不得以流通市值替换 Alpha#056；
- `adv{d}` 是含当日在内、最近 d 个沪深共同交易日原始成交额 CNY 的算术均值；
- 前复权、后复权兼容价不得进入任何公式；原始价格不得混入研究价表达式。

连续研究价以每只证券首个可见 Bar 为 1，单位是指数而非人民币。部分论文公式并非对
逐证券独立缩放不变；这是 REQ-2026-0007 已批准的 A 股输入映射。不得为了追随第三方
输出而静默改用 CNY 复权价。

每日横截面操作使用该日点时 `CoreUniverseDecision.research_member=true` 的集合；
`new_risk_eligible` 是下游生产资格，不能反向改变原始公式 rank。历史 rank 和行业
去均值必须使用每个历史日当时可知的 U0 与行业身份，不能用决策日成员或当前行业回填
历史窗口。

`CoreInputSnapshot.universe_content_hash` 只绑定最终 `decision_date` 的公共
`core_universe_content_hash(current_decisions)`，不得改写为 Alpha101 私有历史哈希。
完整历史成员切片另以 `formulaic-alpha101-u0-history-v1` manifest 和
`history_content_hash` 冻结，精确覆盖有序日期×证券轴、每日截止、每行
`CoreUniverseDecision`、行数和日期范围，并作为独立 sealed dataset slice 进入同一
`CoreInputSnapshot`。入口分别校验最终日公共 U0 身份和历史 manifest；二者不可互相
替代。

## `alpha101-operator-semantics-v1`

### 标量、布尔与数值域

- `abs`、`log`、`sign` 和 `+ - * / > < == || ?:` 按论文含义实现；
- 比较结果数值化为 `1.0` 或 `0.0`；
- 三元表达式和 `||` 使用短路三值逻辑，未知条件不得静默当作 false；
- 普通除法分母为 0 时为 `missing`，不得添加 epsilon；Alpha#101 原式的 `.001`
  是公式常数，不属于实现补丁；
- `log(x)` 要求 `x > 0`；
- 普通 `^` 使用实数幂；负底非整数指数、`0^0` 和零的负指数均失败关闭；
- `^` 右结合且优先于前缀一元正负号：`-2^2 = -(2^2) = -4`、
  `(-2)^2 = 4`、`2^-2 = 0.25`；比较和条件表达式的优先级低于幂与一元运算；
- `signedpower(x,a) = sign(x) * abs(x)^a` 是独立算子，不能退化为普通幂；
  Alpha#001 即使指数为 2 也必须保留输入符号；
- 任一非有限中间值或最终值转为 `missing`，不得夹紧为有限极值。

### 横截面算子

- `rank(x)` 在当日点时研究横截面内仅对 `observed` 值升序排名；
- 并列使用平均秩，并归一化为 `(average_rank - 1) / (n - 1)`；
- 横截面有效值 `n < 2` 时对应结果为 `missing`；
- `scale(x,a)` 使当日 `sum(abs(x)) = a`，默认 `a=1`；L1 范数为 0 时
  `missing`；
- 横截面缺失和 N/A 不得编码为 0，也不得为了提高覆盖删除证券。

### 时间序列算子

- 一“日”是一笔沪深共同交易日位置，不是自然日，也不跳过证券停牌日；
- `delay(x,d)` 取 d 个共同交易日前的值；
- `delta(x,d) = x(t) - x(t-d)`；
- 所有日数参数，包括 delay、delta、correlation、covariance、decay、sum、product、
  stddev 和 `ts_*`，对非整数统一取 `floor(d)`；
- `sum`、`product`、`ts_min`、`ts_max`、`stddev`、`correlation`、
  `covariance`、`ts_rank` 和 `decay_linear` 都要求完整窗口，不得跳过缺失后再向前
  补足 d 个有效值；
- `correlation` 使用 Pearson 相关；`covariance` 和 `stddev` 使用总体口径
  `ddof=0`；零方差为 `missing`；
- `decay_linear(x,d)` 对今天至过去依次使用 `d,d-1,...,1`，再归一化为和 1；
- `ts_rank(x,d)` 是今天的值在完整 d 日窗口内的升序平均百分位秩，规则与
  `rank` 相同；
- `ts_argmax/ts_argmin` 按窗口从旧到新返回 0 起始的首次极值位置；并列取最早出现；
- `min(x,d)` / `max(x,d)` 在第二参数为数值窗口时等同 `ts_min/ts_max`；两个参数均
  为表达式时是逐元素 min/max。解析阶段必须消除该重载歧义。

### 行业算子

`IndNeutralize(x,g)` 在同一交易日、同一准确行业组内对 `observed` 值去均值。行业
身份必须同时满足有效区间和 `available_at <= 当日截止`。输入缺失保持 `missing`；
缺少公式要求的可信层级则为 `not_applicable`。

论文 18 个使用行业中性化的公式严格映射如下：

| 论文层级 | A 股层级 | 公式 |
| --- | --- | --- |
| sector | 点时申万 L1 | #058、#067、#076、#079、#082 |
| industry | 点时申万 L2 | #059、#063、#069、#070、#080、#087、#089、#091、#093、#097 |
| subindustry | 点时申万 L3 | #048、#067、#090、#100 |

Alpha#067 同时要求 L1 和 L3，缺任一级即 N/A。缺某证券的准确层级时，只能把该证券
对应公式标为 N/A；若整个快照缺该层级，则该层级全部相关公式在该日为 N/A。不得向上
回退、使用当前行业、使用主题/概念分类或静默套用近似映射。

当前仓库没有生产级点时申万 L3；因此在真实 L3 数据另立工作包并通过点时验收前，
Alpha#048、#067、#090、#100 必须稳定输出 `not_applicable`。L1/L2 历史回溯若不能
证明当时可知，对相应历史日期同样 N/A。101 个注册定义和输出顺序仍完整保留，不得
删除这些列或改名为 97 维。

首版 L3 能力由 `formulaic-alpha101-industry-capability-v1` 显式冻结为
`unavailable`，版本为 `sw2021-l3-unavailable-until-data-wp-v1`。非空、重命名或补齐
`sw_l3` 字符串都不能启用能力；能力 manifest 与哈希进入 computation manifest 和
原始输出身份。未来只能由独立数据工作包建立新的能力版本，不得自动探测字符串，也
不得回退到 L2/L1。

## 三态、停牌与失败关闭

每个证券、日期、公式只能输出：

- `observed`：所需输入、窗口、数值域和行业层级全部合法；
- `missing`：公式适用，但输入、窗口或数值计算不完整或非法；
- `not_applicable`：公式要求的严格点时行业层级不具备。

适用性门先于数值计算。缺严格行业层级时，即使同日也缺价格，仍优先记录 N/A 原因；
层级具备后才按数值失败记录 missing。状态和稳定原因码必须精确进入原始特征身份。

至少冻结以下原因码：

```text
alpha101_input_missing
alpha101_window_incomplete
alpha101_no_legal_bar
alpha101_zero_denominator
alpha101_zero_variance
alpha101_log_domain
alpha101_power_domain
alpha101_scale_zero_norm
alpha101_cross_section_too_small
alpha101_nonfinite
alpha101_sw_l1_not_point_in_time
alpha101_sw_l2_not_point_in_time
alpha101_sw_l3_unavailable
```

边界规则：

- 停牌或无合法 Bar 时，OHLC、returns 和 vwap 为 missing；
- 若数据明确证明无成交，原始 amount/volume 可以是观察到的 0，`adv` 纳入该 0；
  提供方记录未知时不得复用 U0 容量判断的补零结果；
- 零成交使 `log(volume)`、vwap 和实际零分母路径 missing；
- 涨跌停且有合法 Bar 时不因状态本身删值；一字板只让真正依赖零价差分母的公式
  missing，Alpha#101 仍按原式 `.001` 求值；
- 时间窗口遇到停牌/缺失不得压缩时间或跳日至下一有效 Bar；
- 任一状态不得以数值 0 代替，外层填补和缺失指示属于后续 WP-0072。

## Golden fixture

### 手算算子 fixture

建立小型、人工可复核的 oracle，覆盖：

- rank/ts_rank 并列与 `n<2`；
- argmin/argmax 并列方向；
- Pearson correlation、总体 covariance/stddev、零方差；
- decay_linear 权重；
- min/max 重载、三值布尔和短路；
- scale 零范数；
- 行业去均值、缺层和输入缺失传播；
- log、幂、除零和非有限域。

生产 evaluator 不得生成自己的手算 expected。

### `full_260d`

- 至少 6 只证券、连续 260 个沪深共同交易日；
- 使所有不受行业数据阻断的公式具备完整历史窗口；
- 至少两个各含两只证券的行业组、一个单证券组和一个缺层证券；
- 数据包含非退化 OHLC、量额、总市值、公司行为缩放和可复算 vwap；
- 101 个公式、顺序、状态、原因码和有限数值全部进入 expected。

### `edge_65d`

- 至少 3 只证券、65 个共同交易日；
- 覆盖横截面并列、输入缺失、停牌、明确零成交、一字涨跌停、零方差、除零、
  非法 log/power 和行业缺层；
- 超过 65 日历史需求的公式应精确得到 `window_incomplete`，不得用这个 fixture
  冒充全量数值验收。

### `pit_industry`

- 包含行业 `valid_from` 与 `available_at` 不同日、`[valid_from, valid_to)` 半开有效期、
  未来修订和层级缺失；
- 证明未来行业不能回写历史；
- 证明 L1/L2/L3 不向上回退；
- 精确证明 #048/#067/#090/#100 在无 L3 时 N/A；
- 精确证明全部 18 个行业公式按表内层级传播 N/A。

每个 fixture manifest 记录：

```text
authoritative_source
source_pdf_sha256
formula_registry_version
formula_registry_hash
operator_semantics_version
computation_manifest_hash
l3_capability_status
l3_capability_version
l3_capability_manifest_hash
generator_name
generator_version
dependency_versions
input_hash
expected_output_hash
```

完整 101 式 expected 使用只依赖 Python 标准库的独立 parser、输入映射、算子和
cell-at-a-time evaluator 一次性生成并冻结。full、edge、PIT 的每个
`feature × instrument` cell 均保存 `value/state/reason`，生成器源码、版本、输入身份、
输出内容哈希和生产导入空集同时进入 fixture。主 golden 断言只读取冻结 expected，
不调用生产入口生成 expected；另有 provenance 回归在测试时实际运行结构不同的
grammar-ladder parser、独立输入映射、独立算子和 cell-at-a-time evaluator，并要求
101/101 式、full/edge/PIT 全部 cell 与冻结制品精确一致。包内 scalar reference 仅
作为次级 differential，生产向量 evaluator 不得同时充当唯一 oracle。

## 数值验收

- 公式 ID、规范顺序、AST、原始十进制 token、状态、原因码和布尔结果精确相等；
- 同一实现的纯公式 fixture 使用 `atol=1e-12`、`rtol=1e-12`；
- 独立标量 reference 与向量实现默认同样使用 `1e-12`；
- 只有确实由跨数值库归约顺序导致、且逐公式书面记录原因的比较，才允许放宽到
  `atol=1e-9`、`rtol=1e-9`；
- `1e-9` 是绝对上限，不得全局默认启用，也不得扩大容差掩盖公式、窗口、rank、
  行业或状态错误；
- `observed / missing / not_applicable` 差异不受任何数值容差保护。

## 非目标

- 不实现 WP-0072 的 full/selected 治理、覆盖门、MAD 缩尾、稳健 z-score、填补、
  缺失指示或平行行业/规模中性化诊断；
- 不实现 H20/H60 标签、模型、特征选择、Ridge、LightGBM、O0、CorePolicy 或
  Research Shadow；
- 不补采生产行情、市值或申万 L1/L2/L3 数据，不修改现有 Data 数据集；
- 不建立 `Alpha101-CN`，不使用第三方近似公式，不把缺层公式改成替代层级；
- 不创建或修改 UI、导航、API、调度、数据库迁移或生产 `var/`；
- 不连接 MiniQMT，不读取账户，不创建 StandingMandate、PortfolioTarget、
  OrderPlan、Paper/Live 状态或任何交易动作；
- 不在运行时访问 GitHub、arXiv 或任何网络资源。

## 验收

1. Given 固定论文注册表，When 加载包，Then 精确得到连续、无重复的
   `alpha101_001`～`alpha101_101`，注册表内容哈希可复算。
2. Given 原始十进制窗口，When 构建 AST，Then 原始 token 保留且全部时间参数按
   `floor` 求值，不存在四舍五入。
3. Given 同一 `CoreInputSnapshot` 和同一 260 日面板，When 重复计算，Then 101 维
   envelope、逐行身份、状态和数值完全可复算。
4. Given 65 日边界面板，When 计算长窗口公式，Then 明确
   `alpha101_window_incomplete`，不跳过停牌、不向前寻找额外有效 Bar。
5. Given 缺少可信 L1/L2/L3，When 计算 18 个行业公式，Then 严格按层级矩阵输出 N/A，
   不回退、不填零、不删除公式。
6. Given 零量、停牌、涨跌停、零分母、零方差、非法 log/power 或非有限结果，When
   计算，Then 按稳定原因码失败关闭。
7. Given 未来 U0 或行业事实，When 回算历史日期，Then 历史 rank 和
   `IndNeutralize` 不受未来事实影响。
8. Given full、edge、PIT 和手算 fixture，When 对比 expected，Then 状态精确相等，
   数值满足 `1e-12` 默认门，任何 `1e-9` 例外均为逐公式登记且不超过上限。
9. Given 包测试，When 运行默认受影响检查，Then 不访问网络、不加载 MiniQMT SDK、
   不执行交易，且总耗时目标小于 90 秒。

## 检查

```text
uv run pytest \
  tests/unit/test_formulaic_alpha101_registry.py \
  tests/unit/test_formulaic_alpha101_operators.py \
  tests/unit/test_formulaic_alpha101_evaluator.py
uv run pytest tests/unit/test_core_data_semantics.py tests/unit/test_architecture.py tests/unit/test_contracts.py
make docs-check
git diff --check
```

所有默认检查必须使用本地小型 fixture，并在目标 90 秒内完成。全历史重建、生产数据
补采、长回放和任何 Paper/Live 工作都不属于本工作包检查。

## 交接

派发前由主控确认本工作包独占 `formulaic_alpha101/**` 和三份指定测试文件。完成后由
主控复核论文 PDF hash、101 公式注册表、算子语义、行业 N/A 矩阵、260/65/PIT golden
以及三态失败关闭，再允许 WP-0072 消费 F2 原始 envelope。本包完成不表示申万 L3
数据已具备，也不授权 MiniQMT、Paper、Live 或真实资金。

## 实施结果（2026-07-30）

- 已从 arXiv v3 原始 PDF 独立提取 Alpha#001～#101；去除 PDF 分页号并仅归一化空白
  后，101/101 条与本地原始公式逐字一致。PDF 仍为 244,416 字节，SHA-256 与本包
  登记值一致。
- 本地严格公式注册表固定为
  `sha256:b2c9dcbeb8c81449cc2e60227aaf87da17a58bb51a04d0eca2468c594fa34a5c`；
  WP-0070 公共名称/顺序/版本注册表仍为
  `sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5`。
  最大完整输入需求按“所需会话数”固定为 252，不再误记为 251 个回看偏移。
- 包内 `computation_manifest_hash` 固定为
  `sha256:26625f1b77bd63cc0064207e1612e2916ff99682aa4685807beeff3c735adc61`，
  同时绑定 PDF 来源、101 条原始公式与 AST、算子语义、公共包规格、
  `core-data-semantics-v1`、`U0-v1`、严格申万 L1/L2/L3 映射、输入映射和两个
  行情/行业切片、一个历史 U0 manifest 哈希语义、表达式语法和 L3 capability；
  调用方不能注入替代 manifest。
- L3 capability manifest 固定为
  `sha256:afce84df4dfc634b6b93fc371f5f68dc238dd921c3fc05f6a09f3964cf572c73`
  且状态为 `unavailable`。注入、重命名或补齐任意 L3 字符串后，#048/#067/#090/#100
  仍稳定 N/A，97 个非 L3 公式不受影响；能力或哈希伪造会改变受保护身份并失败关闭。
- bar 与行业行分别使用 `alpha101-daily-input-slice-v1` 和
  `alpha101-industry-input-slice-v1` 内容身份，并与 `CoreInputSnapshot` 的准确数据集
  哈希和行数核对。同一核心输入下修改 OHLCV/amount/cap、可用时间或行业记录会在入口
 失败关闭；每日 U0、共同日历和历史行业截止继续使用 WP-0070/点时合同。
- 已删除第二套 U0 identity：核心输入只使用最终日公共
  `core_universe_content_hash`；完整日序列另由
  `formulaic-alpha101-u0-history-v1/history_content_hash` manifest 及独立数据切片
  绑定。最终成员、历史成员、重复键、未来截止和非规范输入顺序攻击分别失败关闭，
  fixture 使用公共 helper 构造诚实 snapshot。
- full、edge、PIT 共冻结 1,212 个独立 golden cell，逐一保存
  `value/state/reason`。生成器含不使用生产 precedence table 的 grammar-ladder
  parser、合成输入映射、算子和 cell-at-a-time evaluator，不导入生产 Alpha101 模块；
  测试实际重跑第三参考并对 1,212/1,212 cell 精确比对。生产向量实现先对冻结 golden
  验证，再与包内 scalar reference 作次级 differential。parser、close 输入映射和
  除法算子单点故障注入均能触发 golden 失败。
- 生产 parser 和独立 parser 分别执行并证明 `-2^2=-4`、`(-2)^2=4`、
  `2^-2=0.25`、`--2=2`、`2^3^2=512` 以及比较/条件与幂结合；修复不依赖公式文本
  恰好避开歧义。full fixture 保持 6 证券×260 共同交易日，97 个非 L3 公式每式至少
  2 个 finite observed cell；四个严格 L3 公式各 6 个 cell 全为 N/A。
- 独立生成器源码身份固定为
  `sha256:30dcea7041aa3540e4b93714cd61b8bee1d242a101abc506f6c5efea39a31e55`；
  full、edge、PIT 的独立输入哈希依次为
  `sha256:5dbcb1dbf29d01ee85296bf21b4a78750128f8a9e70fbbff0b3c4781296393f7`、
  `sha256:36d6977b447aba35f905e8bab451c6fc3610fa0631e38575967ad17f0e89b9ba`、
  `sha256:dafe6e27d2e65e513b988ebcab04d134cd9679314a6c9e8db24c12a36c087cad`；
  full、edge、PIT 的冻结 cell 内容哈希依次为
  `sha256:2da2c8bcca4b41aef4815126a2da8831c38c114cbbaf42238164b5e40e8e067e`、
  `sha256:61dd2fceb05f38b18843a87e2591cfbcc7acaa7fc8082ebb793afa693e62a572`、
  `sha256:70fd69b3d56658f88b80f9e41c715c6bb80e49d3457c673eacd23618c00de758`。
- 已覆盖 3 证券×65 日停牌、零成交、一字板、窗口不完整、零方差、除零、非法 log、
  非有限结果和严格行业缺层；`observed/missing/not_applicable` 不使用数值占位。
  缺申万 L3 时 #048/#067/#090/#100 稳定 N/A，不回退到 L2/L1 或任何 A 股近似身份。
- 已增加前缀因果性、公式分块/逆序幂等、证券局部隔离、共同日历删日、未来 bar/行业、
  U0 翻转、输入内容篡改、输出行与 manifest 篡改反例。全部数值比较继续使用
  `atol=rtol=1e-12`，没有 `1e-9` 例外。
- `factory.py`、registry/provenance 测试和端到端 evaluator 测试按 fixture 构造、
  来源身份与完整合同矩阵分责，均低于 500 行阻断阈值，未机械压行或拆出无责任边界
  文件。独立 golden JSON 属生成制品，生产模块与函数均低于阻断阈值。

论文没有唯一规定 rank 归一化、总体/样本统计、并列、非整数窗口、三值短路和中国行业
映射；这些已按本包既有批准决定失败关闭固化，没有引入新的用户选择。真实点时申万 L3
仍是外部数据门，本提交只保证缺失时的严格 N/A，不声称生产数据已经具备。
