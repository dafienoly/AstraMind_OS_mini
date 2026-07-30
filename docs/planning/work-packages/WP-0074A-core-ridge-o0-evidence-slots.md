# WP-0074A：核心 Ridge O0 回放、C2 证据与 LightGBM 槽位

- 版本：1.0.0
- 状态：已授权，依赖门等待 WP-0073A 集成
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5C、5D
- UI 提案：不适用
- 所有者：后续核心证据工作树 / Strategy Research

## 目标

为 WP-0073A 的 B0/Ridge OOF 与绝对收益校准建立唯一 broker-free 研究执行语义：
按 H20/H60 独立 50,000 元袖套运行 O0、100 股/容量/行业/费用约束和 C0～C3 回放，
形成开发期 C2 候选比较、Ridge 决赛者、联合资格及最多四个
`CoreLightGBMSlotManifest`。

本包只冻结 Ridge 和 LightGBM 父级槽，不形成最终 `CorePolicyVersion`，不运行
LightGBM。WP-0073B 完成挑战模型后，WP-0074B 使用同一 O0/C2 引擎做最终比较，避免
模型层和组合层各自实现一套成本或执行假设。

## 启动门

1. WP-0073A 已集成，B0/Ridge 候选、OOF、校准和环境身份完整；
2. 每个候选具备准确 H20/H60、特征视图、季度版本和开发期冻结边界；
3. 所有决策日具备原始 T+1 开盘、停复牌/涨跌停、点时 SW L1、20 日成交额中位数和
   公司行动；缺任何关键输入时对应周失败关闭；
4. 工作树从最新主线建立，不修改 Portfolio & Risk 或 Trading Execution。

## 非目标

- 不训练、重训或修改 B0/Ridge/LightGBM，不改变特征和校准；
- 不形成最终 H20/H60 联合 CorePolicy，不运行弱信号/恢复状态机；
- 不创建公共 `PortfolioTarget`、`OrderPlan`、StandingMandate 或券商委托；
- 不连接 MiniQMT，不运行 Research Shadow、Paper/Live 或生产回放；
- 不创建 UI，不修改生产 `var/`，不补采行情或行业数据；
- 不自动晋级候选，不让训练损失、毛收益或单一 RankIC 替代 C2。

## 允许文件

- `src/astramind_mini/strategy_research/core/o0_evidence/**`
- `tests/unit/test_core_o0_costs_*.py`
- `tests/unit/test_core_o0_ridge_*.py`
- `tests/golden/test_core_o0_ridge_evidence.py`
- `tests/fixtures/core/o0/**`
- 本工作包及直接追踪状态

不得修改 WP-0073A、公共合同、Portfolio & Risk、Trading Execution、Data、三个因子
包、根配置、数据库迁移、`composition.py`、前端或生产数据。本包的 O0 是研究回放
语义，不冒充生产组合服务；WP-0074B 再建立到 Portfolio & Risk 公共契约的单向适配。

## 唯一制品

本子包拥有：

- `CoreCostSchedule`，身份 `core-cost-cn-a-share-v1`；
- `CoreO0ResearchSpec`，身份 `core-o0-research-v1`；
- `CoreExecutableResearchLedger`；
- `CoreCandidateEvidence`；
- `CoreRidgeFinalistManifest`；
- `CoreLightGBMSlotManifest`；
- `CoreCommonExclusionLedger`。

全部使用规范 JSON 和 SHA-256 内容身份，绑定准确模型/校准、DataSnapshot、决策日、
原始价格、费用版本、滑点情景、U0/行业、容量、初始现金、订单/持仓/公司行动、NAV、
排除原因和代码身份。不同成本情景、周期或候选不得共用证据 ID。

## 费用与滑点

所有订单金额与费用使用 `Decimal`，输入价格和金额先按数据合同精度转 Decimal。每个
费用分量独立按人民币分 `ROUND_HALF_UP`，再求和：

- 股票全佣 `commission = max(5.00, notional * 0.000086)`，`notional > 0` 时适用；
- 全佣已含经手、证管和过户，不重复叠加；
- 卖出印花税：2018-01-01～2023-08-27 为 `0.001`，依据
  [2008 年起千分之一单边征收](https://www.mof.gov.cn/zhengwuxinxi/caizhengxinwen/200809/t20080919_76432.htm)；
  2023-08-28 起为 `0.0005`，依据
  [财政部、税务总局 2023 年第 39 号公告](https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211343/content.html)；
- 买入不收印花税；
- C0/C1/C2/C3 每边滑点分别为 5/10/20/50 bp；
- 买入执行价 `raw_open * (1 + bps/10000)`，卖出执行价
  `raw_open * (1 - bps/10000)`；
- 费用规则按交易日期选择，后来税率不能改写旧证据。

当前核心证据最早使用 2018 年，早于 2018-01-01 的法定费用必须先扩展版本表和 golden，
不得外推。C2（20 bp/边）是所有资格硬门，其他情景只作压力诊断。

## 决策、订单和账本时钟

- T 日收盘后冻结预测，T+1 共同交易日开盘使用原始可成交价格；
- 错过 T+1 开盘不追价、不补单，该周期保持原仓或现金并记录；
- H20/H60 比较阶段分别使用独立 50,000 元初始现金和独立账本；
- 同一周期内先把目标与已有持仓求净额，再按 100 股向零取整；
- 买卖相反贡献在最终联合前不跨周期净额；WP-0074B 才执行 H20/H60 合并；
- 买入前预留佣金与滑点，卖出按实际税费入账；
- 已持证券的公司行动、现金和估值进入每日 NAV；退市、停牌、涨跌停按点时执行状态
  失败关闭或保持持仓，不删除历史行；
- A 股 T+1：当日新买数量不可同日卖出；周度计划一般无同日反向，负测必须阻止该行为。

本包只生成研究订单行，不创建公共 `OrderPlan`。

## 容量、可交易与约束

最终每个单边净订单：

`abs(order_notional) <= 0.001 * median_amount_20`

`median_amount_20` 使用 WP-0070 冻结值，停牌/无成交日按 0。超限只向零缩到合法
100 股或留现金；不得拆单、跨日追单或把容量不足证券换成未登记候选。

每周期研究袖套先按校准后绝对净预期收益排序，要求：

- 候选仍在 U0 且 `new_risk_eligible=true`；
- 数据、模型、校准、方向和执行输入健康；
- 新风险的完整预期往返 C2 收益严格大于 0；
- 已持仓继续持有不重复计已发生买入成本；
- 替换比较“继续持有旧股”与“卖旧买新”的增量 C2。

为选择模型配置，每个 H 周期单独运行固定 50,000 元袖套，最多五只、单股对该袖套
目标不超过 50%（对应联合 100,000 元的最终 25%），SW L1 对该袖套目标不超过 80%
且最多两只（对应联合 40%）。真正 H20/H60 合并后的 25%/40% 门由 WP-0074B 再检查；
单袖套结果不能宣称最终组合合规。

## 单周期 O0 研究转换

对每个候选、每个周期：

1. 把校准收益转换为
   `score_5d = exp((5/H) * ln(1 + expected_net_return_H)) - 1`；
2. `expected_net_return_H <= -1` 或非有限时系统失效；
3. 过滤不可新增风险和完整往返 C2 预期净收益不正者；
4. 按 `score_5d` 降序、instrument ID 字典序打破并列；
5. 新买只考虑 Top5；已有持仓 Top10 内继续持有；
6. 替代者在 Top5、旧股跌出 Top10且替换边际 C2 为正时，最多一次自愿替换；
7. 对入选证券等额分配袖套预算，按约束、现金、100 股、费用和容量逐步向零修复；
8. 不可行部分留现金，禁止归一化到剩余股票。

这只是为模型证据服务的单周期 O0。弱信号两周确认和 H20/H60 联合排名属于 WP-0074B。

## 可执行 NAV 与统计

每日 NAV 使用原始可交易价格、现金、整数手持仓、费用和公司行动：

`NAV_t = cash_t + sum_i(quantity_i * raw_close_i,t)`

收益、CAGR、MDD、Calmar 和单边换手严格按 REQ-2026-0007 第 15 节：

- 任一单期收益 `<= -1` 时证据失败关闭；
- `CAGR = (ending_NAV / starting_NAV)^(252 / N_common_sessions) - 1`；
- `MDD = min_t(NAV_t / running_max_NAV_t - 1)`；
- `Calmar = CAGR / abs(MDD)`，零 MDD 特例按需求；
- 单边换手为股票加现金权重变化绝对值和的一半，不计被动价格漂移；
- 初次建仓和风险退出单列。

## Ridge 资格、联合门和槽位

每周期对 WP-0073A 候选：

1. 数据/校准/方向/确定性/回放覆盖先失败关闭；
2. 开发期 C2 整段净收益必须大于 0；
3. 选择同配置九个 alpha 中 C2 年化净收益增量 bootstrap 第 10 百分位最高者；
4. 并列依次为低换手、少特征、lineage ID 字典序；
5. 六个单包配置分别形成证据，选出最佳 F0、Alpha158、Alpha101；
6. 三个 selected 两包联合分别与较强单包比较；
7. 至少一个两包联合 C2 总收益为正且年化增量大于 0，才打开三包联合；
8. 选出最佳已允许联合。

alpha 和配置比较都使用相同周末、共同排除账本和配对圆形移动区块：H20 为 4 周，
H60 为 12 周，10,000 次；候选特有缺失不能 pairwise 删除。用于选择的“第 10
百分位”是配对 `ΔCAGR_pp` 分布的 10th percentile。

每周期最多发布四槽：最佳 F0、Alpha158、Alpha101、最佳已允许联合。槽位绑定准确
Ridge 父级、特征视图、alpha、周期、训练计划、O0、C2 和证据 ID；没有合格父级的槽
明确关闭，不递补。

## Golden 与负向证明

fixture 至少覆盖 2018～2025 的税率切换边界、两周期和：

- 最低 5 元、佣金/税/滑点逐分取整、买卖方向和四情景；
- 100 股、现金不足、容量缩量、停牌/涨跌停、错过 T+1 和公司行动；
- Top5/Top10、替换边际、一次替换、现金不归一化；
- 九 alpha、六单包、三两包、三包门和四槽关闭；
- 共同无效周与候选特有缺失、区块绕回和 seed；
- 追加未来数据后旧订单、NAV、证据、槽位和哈希不变。

费用和小账本使用逐笔手算 Decimal oracle；bootstrap 使用独立参考实现。金额、数量、
状态、原因、ID 和哈希精确相等；收益/NAV 比率使用 `atol=rtol=1e-12`。

## 验收

1. C0～C3、佣金、最低 5 元和历史印花税精确且不重复收费。
2. 原始执行价、T+1、100 股、容量、停牌/涨跌停、公司行动和现金通过正负测试。
3. 单周期 O0 不删除失败证券、不追价、不归一化且只形成研究订单。
4. 九 alpha、单包→两包→有条件三包和四槽预算不可扩张。
5. C2/O0 而非训练损失决定 Ridge/槽位；候选缺失不能 pairwise 美化。
6. 同一输入幂等，任何模型、校准、成本、数据、订单或代码变化重标识。
7. 导入图不包含 LightGBM、Portfolio & Risk 内部模块、Trading Execution、MiniQMT、
   账户、前端或网络。

## 检查

```text
uv run pytest tests/unit/test_core_o0_costs_*.py \
  tests/unit/test_core_o0_ridge_*.py tests/golden/test_core_o0_ridge_evidence.py -q
uv run pytest tests/unit/test_core_modeling_*.py tests/unit/test_architecture.py -q
uv run ruff check src/astramind_mini/strategy_research/core/o0_evidence \
  tests/unit/test_core_o0_costs_*.py tests/unit/test_core_o0_ridge_*.py \
  tests/golden/test_core_o0_ridge_evidence.py
uv run mypy --strict src/astramind_mini/strategy_research/core/o0_evidence
make docs-check
git diff --check
```

## 授权与交接

主控复核费用、执行约束、账本、证据配对、联合门和槽位身份后集成，并在独立提交中准备
LightGBM 根依赖，再释放 WP-0073B。本包完成不表示最终策略、生产激活、Research
Shadow、Paper 或交易授权。

本授权不包含生产数据变更、新 UI、MiniQMT、账户、StandingMandate、Research Shadow
实际运行、Paper/Live 或订单。
