# WP-0071A：AstraMind F0 原生 24 因子公式包

- 版本：1.1.0
- 状态：已完成、通过四轮独立复核并集成
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5A
- UI 提案：不适用
- 所有者：Worker B / Strategy Research

## 目标

实现 `astramind-f0-v1` 的 24 个规范原始因子。实现只消费 WP-0070 冻结的
`CoreInputSnapshot`、`U0-v1` 决策和公共原始特征输出 builder，逐证券、逐决策日生成
固定顺序的 `observed / missing / not_applicable` 原始结果，并以 golden fixture
证明公式、点时财务、研究价格、行业适用性和内容身份不会漂移。

## 非目标

- 不实现 full/selected、缩尾、填补、标准化、外层中性化或覆盖筛选；
- 不实现 B0、Ridge、LightGBM、D1/D3/D5、H20/H60、O0 或 CorePolicy；
- 不建设 F0-FIN，不把普通企业财务公式强套银行、保险或券商；
- 不修改 WP-0070 公共合同，不直接查询 Data 内部模块或生产 `var/`；
- 不补采财务、股利、行业或行情，不创建 UI；
- 不连接 MiniQMT，不进入 Research Shadow、Paper/Live，不生成组合、订单或账户动作。

## 允许文件

- `src/astramind_mini/strategy_research/core/f0/**`
- `tests/unit/test_core_f0_*.py`
- `tests/golden/test_core_f0_formulas.py`
- `tests/fixtures/core/f0/**`
- `docs/planning/work-packages/WP-0071A-astramind-f0-formula-package.md`

不得修改 `strategy_research/core` 的公共合同、`contracts/**`、`data/**`、
`composition.py`、数据库迁移、根配置、前端或其他因子包。调用方从
`strategy_research.core.f0` 导入，不修改高争用的 `core/__init__.py`。

## 固定身份与顺序

包身份为 `astramind-f0-v1`，规范维数为 24。注册表按 REQ-2026-0007 第 6 节顺序固定：

1. `EP_TTM`
2. `BP`
3. `SP_TTM`
4. `DY_TTM`
5. `ROE_TTM`
6. `ROA_TTM`
7. `OPERATING_MARGIN_TTM`
8. `OCF_TO_NET_INCOME_TTM`
9. `ACCRUALS_TO_ASSETS_TTM`
10. `DEBT_TO_ASSETS`
11. `REVENUE_TTM_YOY`
12. `NET_PROFIT_TTM_YOY`
13. `OCF_TTM_YOY`
14. `MOM_20_5`
15. `MOM_60_5`
16. `MOM_120_20`
17. `INDUSTRY_REL_MOM_60_5`
18. `REV_5`
19. `RESIDUAL_REV_20`
20. `REALIZED_VOL_20`
21. `DOWNSIDE_VOL_60`
22. `LOG_MEDIAN_AMOUNT_20`
23. `TURNOVER_MEAN_20`
24. `AMIHUD_20`

以上有序 ID 与统一 `feature_definition_version=1.0.0` 的公共注册表哈希固定为
`sha256:5fd8435ecfd1dee75ca078a6aed7cfd47a257efa427394766938ba1fa5598b9b`，
必须与 WP-0070 的 `CoreFeaturePackageSpec.required_definition_registry_hash` 一致。

注册表保存 ordinal、ID、版本、家族、预登记 B0 方向、规范公式文本、输入依赖、最大
回看、适用范围和失败原因码。以上任一项变化必须创建新包身份，不能继续称为
`astramind-f0-v1`。

## 输入、公式与点时规则

- 价格与收益只使用连续研究价格指数；成交额、成交量、换手率和市值使用原始点时值；
- `Med20`、`Mean20`、动量、反转和波动窗口按完整沪深共同交易日索引计算，不得删除
  停牌或缺 Bar 后压缩窗口；
- 财务流量使用正确构造的 TTM，存量使用最新已公开期末值；准确公告时间之后才可见，
  只有公告日期时从下一共同交易日收盘后可见，修订不回写；
- TTM 流量使用“本年累计 + 上年全年 − 上年同期累计”；缺期、不可比口径或不完整
  累计值为 `missing`，不得按月份机械年化；
- ROE/ROA 在期初期末均可用时使用平均值；缺任一必要期末值即 `missing`；
- `DY_TTM` 只纳入决策时点前 12 个月已公开且已具备实施依据的现金股利；
- 增长比率要求当前与上年同期分母同号且上年同期绝对值大于 0，否则 `missing`；
- `INDUSTRY_REL_MOM_60_5` 与 `RESIDUAL_REV_20` 使用历史日当时可知的 SW L1 和 U0；
  缺准确行业身份时为 `not_applicable`，不得用当前行业回填；
- `RESIDUAL_REV_20` 对个股简单收益、U0 等权收益和 SW L1 等权收益做带截距 OLS，
  至少 15 个共同有效观测；保存 20 日残差和的负值；
- `REALIZED_VOL_20` 使用日对数收益样本标准差 `ddof=1` 并乘 `sqrt(252)`；
  `DOWNSIDE_VOL_60` 使用简单收益和 `sqrt(252 * mean(min(r,0)^2))`；
- Amihud 无成交日不构造单日比值，是否形成 20 日值由完整窗口覆盖门决定；容量模块
  的无成交补零不得进入因子输入；
- 分母为零、非法符号、非有限结果或必要输入不足均为 `missing`，不得添加 epsilon。

普通企业财务因子对银行、保险和券商标记 `not_applicable`；动量、反转、低波和流动性
因子仍可适用。行业适用性门优先于一般输入缺失，并使用稳定原因码。

## 实现边界

建议子包结构：

```text
f0/
  __init__.py
  registry.py
  inputs.py
  financials.py
  market_factors.py
  regression.py
  evaluator.py
  reasons.py
```

生产 API 接收已冻结的核心输入和规范化点时观测，不自行加载文件、访问网络或重建 U0。
计算器输出 `CoreRawFeatureRowDraft`，再调用 WP-0070 公共 builder 形成统一
`CoreRawFeatureEnvelope`。原始包不得自行生成另一种 FeatureSnapshot、行合同或清单。

## Golden 与负向证明

fixture 至少包含 6 只证券、跨 3 个行业、至少 260 个共同交易日，并覆盖：

- 正常企业、银行/保险/券商、行业变更和新股边界；
- 只有公告日期、准确公告时间、后来修订、缺季度、负分母和累计报表 TTM；
- 分红公告与实施依据时点；
- 停牌、零成交、缺 Bar、涨跌停、公司行为前后的连续研究价；
- OLS 满足/不足 15 个共同观测、行业缺失、零方差、除零和非有限结果；
- 追加未来行情、财务、行业或修订后，原截止日前结果与内容身份完全不变。

手算 oracle 独立给出关键财务、动量、波动、Amihud 和 OLS 结果；不得由生产 evaluator
自我生成全部期望值。ID、顺序、状态、原因码和哈希精确相等；纯公式有限值使用
`atol=rtol=1e-12`。若独立数值库的 OLS 归约存在已登记差异，单项上限为 `1e-9`，
不得放宽三态或身份比较。

## 验收

1. 注册表恰好 24 个唯一 ID，顺序、公式、方向和家族与需求完全一致。
2. 同一核心输入重复计算幂等；输入、截止、注册表、行内容或顺序变化会重标识。
3. 财务公告、修订、TTM、行业和历史 U0 均通过点时负测，未来记录不可见。
4. 金融企业财务项明确 `not_applicable`，但四类市场因子不被整体删除。
5. 缺失、停牌、无成交、除零和非有限值不会被写成 0 或进入哈希。
6. 三态原始行通过 WP-0070 公共 builder，24 维不含指示列或处理后列。
7. 运行时导入树不包含 Data 内部模块、网络、MiniQMT、Portfolio & Risk 或 Execution。
8. 默认聚焦检查在 90 秒内；完整历史重建不是默认测试的一部分。

## 检查

```text
uv run pytest tests/unit/test_core_f0_*.py tests/golden/test_core_f0_formulas.py -q
uv run pytest tests/unit/test_core_universe.py tests/unit/test_core_data_semantics.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/f0 tests/unit/test_core_f0_*.py tests/golden/test_core_f0_formulas.py
uv run mypy --strict src/astramind_mini/strategy_research/core/f0
make docs-check
git diff --check
```

## 实施结果

- 已在独立 `f0` 子包实现 24 个固定顺序原始公式，输出只通过 WP-0070 v1.1
  `build_core_raw_feature_envelope` 形成统一三态 envelope，并直接校验唯一
  `CoreCommonCalendar` 完整日期序列。
- 完整计算语义 manifest 固定为
  `sha256:a404abe527f5b50c66c974d4520529a1ec0a4aaa3049daea28fea66900f6900f`；
  它覆盖 24 个定义、公式/方向/家族/输入/回看/适用性/失败原因以及逐字段 TTM、
  即时项、跨字段可比口径、财务/分红稳定修订归并和全部市场窗口、逐日收益、
  行业截面覆盖、几何复合、OLS 求解/rcond/rank/奇异/归约、年化与 Amihud 常量，
  也冻结行情最大权威时点归并及公司分类的有效区间、分层选择和并列冲突策略。
- 当前 U0 决策集使用 WP-0070 公共规范哈希算法精确绑定
  `CoreInputSnapshot.universe_content_hash`，全历史 U0 的日/证券身份必须唯一。
  财务流量逐指标独立选择自身最新可见累计期；ROE、ROA 和应计项要求 TTM 期与平均
  存量期精确一致，跨字段期间或 `comparable_scope` 不一致失败关闭。财务与分红的
  稳定修订身份不包含公告时点或 payload；同身份完全相同记录确定性去重，任一字段
  冲突失败关闭。不同 revision 只按权威可用时间选择，同一最大可用时点的等价计算
  payload 合并、冲突关闭，绝不以 `revision_id` 字典序裁决。
- golden 使用 260 个固定沪深共同交易日、6 只证券和 3 个行业；测试中的手算公式/
  三态 oracle 独立构造全部 144 行，再经公共 builder 推导行与输出身份，不调用生产
  evaluator 生成期望。fixture 记录受审计 oracle 的版本与代码身份、权威需求源提交，
  并从完整 `F0InputBundle` 独立重算输入指纹。另覆盖公告生效/修订、分红修订、停牌/零成交、缺 Bar、
  涨跌停、公司行动连续研究价、零方差、除零、非有限、行业变化与新股历史 U0。
- 本结果不包含处理后特征、选择、模型、组合、UI、生产补采、MiniQMT、账户、
  Research Shadow、Paper/Live 或订单动作。

## 交接

主控已复核公式注册表、点时 fixture、三态分布、内容身份和运行时导入树，并在四轮
独立复核依次关闭 U0/期间、修订归并、计算 manifest、行情/分类顺序依赖和 golden
血缘缺口后集成。
本包完成只表示 F0 原始公式层可复算，不表示 WP-0072 的处理/筛选、模型、组合、UI、
生产补采或任何券商动作已完成或获准。
