# WP-0070：核心 U0、点时数据语义与特征合同

- 版本：1.1.0
- 状态：已完成并通过主控复核
- 需求：REQ-2026-0007 v2.3.0
- 阶段：5A
- UI 提案：不适用
- 所有者：Worker C / Strategy Research

## 目标

建立周度核心研究后续所有因子包共用的最小稳定腰部：可复算的 `U0-v1` 点时成员与
新风险资格、`core-data-semantics-v1` 输入语义，以及绑定一个不可变 `DataSnapshot`
和周度截止的核心输入身份。F0、Alpha158、Alpha101 必须消费同一合同，不能各自重写
股票池、价格、行业、缺失或可用时间规则。

## 非目标

- 不计算 F0、Alpha158、Alpha101 或任何模型预测；
- 不实现 full/selected、Ridge、LightGBM、H20/H60、O0 或 CorePolicy；
- 不创建新页面，不修改导航或现有 UI；
- 不连接 MiniQMT，不读取账户，不修改生产 `var/`，不建立 Paper/Live 或订单；
- 不把分钟/Tick、当前会话投影、北交所、新股或 ETF 放入首期核心生产池；
- 不修改当前 WP-0041 MiniQMT 数据管线重构拥有的目录。

## 允许文件

- `src/astramind_mini/strategy_research/core/**`
- `tests/unit/test_core_universe.py`
- `tests/unit/test_core_data_semantics.py`
- `tests/unit/test_core_feature_identity.py`
- `tests/unit/test_core_common_calendar.py`
- `tests/fixtures/core/**`
- 本工作包及其直接需求/追踪状态

不得修改 `src/astramind_mini/contracts/**`、`data/**`、`composition.py`、
`strategy_research/public.py`、数据库迁移、根配置、生产数据和前端。若实现证明必须
改变共享契约，停止并返回主控，不在本包扩大范围。

## 合同与唯一所有者

Strategy Research 的 `core` 子包拥有：

1. `CoreUniverseSpec`：冻结 `U0-v1` 的板块、成熟期、状态、流动性和覆盖规则；
2. `CoreUniverseDecision`：逐证券记录 `research_member`、`new_risk_eligible`、
   `diagnostic_pool`、原因码和输入截止；
3. `CoreDataSemantics`：冻结连续研究价、原始价量、点时行业、财务可用时间和三态缺失；
4. `CoreInputSnapshot`：绑定 `DataSnapshot`、周度决策日、截止时间、共同交易日历、
   数据语义、U0 版本、数据集引用、行数、日期范围和内容身份；
5. `CoreFeaturePackageSpec`：只声明规范包身份、规范维数和输入语义；本包不生成因子值。

后续包只能导入该子包公开入口，不得复制资格或语义常量。

共同交易日历使用唯一的 `CoreCommonCalendar` / `core-common-calendar-v1` 公共合同：
内容身份同时绑定日历 ID 和截至决策日的完整有序共同交易日序列。
`CoreInputSnapshot` 直接保存该不可变日历证据，F0、Alpha158 和 Alpha101 只能消费
这一个序列与哈希，不得在各自包内定义不同的日历哈希算法。删除、插入、调序任一
共同交易日都会创建不同身份；伪造序列但沿用旧哈希必须在合同构造时失败关闭。

原始因子制品除包规格和特征 ID 注册表外，还必须绑定
`computation_manifest_hash`。该哈希由各因子包根据自己的完整计算语义生成：
F0 覆盖全部公式与财务字段口径，Alpha158 覆盖固定 Qlib 提交、表达式和算子语义，
Alpha101 覆盖原论文身份、规范 AST、严格行业算子及版本。只改公式而保留相同特征
名称时也必须产生新制品身份。

## 行为

### U0-v1

- 只纳入上交所主板/科创板、深交所主板/创业板的点时 A 股；
- 成熟期按上市日起 252 个沪深共同交易日计算，不按自然日近似；
- ST、`*ST`、退市整理或状态未知不能新增风险；
- 最近 20 个共同交易日原始成交额中位数至少 2,000 万元；停牌、无成交或缺合法 Bar
  的日期按 0，少于 20 日直接不合格；
- 暂停证券仍保留在历史研究面板和已有持仓诊断，但 `new_risk_eligible=false`；
- 北交所进入明确诊断池，新股进入独立诊断池，均不静默混入生产候选。

### core-data-semantics-v1

- OHLC 与收益使用连续研究价格指数；
- 原始价量只用于成交、流动性、容量和执行约束，复权兼容价只供审计；
- 行业必须是决策时点可知的 SW2021 身份，缺失时严格行业算子失败关闭；
- 财务记录按公告实际可用时间生效，只有日期时从下一共同交易日收盘后可用，修订不回写；
- 因子值状态只有 `observed / missing / not_applicable`，另有冻结覆盖门，禁止用 0 填充未知；
- 当前会话、形成中分钟和未封存 Tick 不得进入核心输入身份。

## 验收

1. Given 同一冻结输入，When 重复构造 U0 与 `CoreInputSnapshot`，Then 内容身份完全一致。
2. Given 未来公告、后来修订、未来行业归属或截止后的行情，When 构造历史决策日输入，
   Then 对应记录不可见，并有负向测试证明。
3. Given 新股、北交所、ST、状态未知、停牌、少于 20 日或流动性不足证券，When 评估，
   Then 研究成员、生产新风险资格和诊断池不会混为一个布尔值。
4. Given 无成交日，When 计算 20 日成交额中位数，Then 该日按 0；但因子输入保持真实
   缺失状态，不把成交约束口径回写成因子值。
5. Given 数据集引用、截止、行数、日期范围或内容发生变化，When 冻结输入，
   Then 发布新身份；旧身份不被覆盖。
6. Given 三个因子包消费同一 `CoreInputSnapshot`，When 校验共同交易日，
   Then 三包读取同一个完整 `CoreCommonCalendar`；所有证券同时删除一个中间交易日
   也必须因日历身份不匹配而失败，不能静默压缩窗口。
7. Given 因子 ID 和输出值不变但完整公式、源版本或算子语义变化，When 冻结原始
   因子制品，Then `computation_manifest_hash`、`FeatureSnapshot` 和 manifest 身份
   必须变化；沿用旧身份必须失败关闭。
8. 核心合同不导入 MiniQMT SDK、Market Regime 内部模块、Portfolio & Risk 或
   Trading Execution；不创建 `PortfolioTarget`、`OrderPlan` 或券商动作。

## 检查

```text
uv run pytest tests/unit/test_core_universe.py tests/unit/test_core_data_semantics.py \
  tests/unit/test_core_feature_identity.py tests/unit/test_core_common_calendar.py
uv run pytest tests/unit/test_architecture.py tests/unit/test_contracts.py
make docs-check
git diff --check
```

## 交接

完成后由主控复核合同维度、原因码、点时负测和内容身份，再从最新集成提交释放
WP-0071A/B/C。三个因子包可以并行计算，但不得并行修改本包合同。

## 实施结果

- `strategy_research/core` 已建立唯一公开入口，冻结 `U0-v1`、
  `core-data-semantics-v1`、`CoreInputSnapshot` 和三包规范身份；
- U0 规格整体冻结为沪深 `stock/a_share`、固定板块顺序、252 日成熟期、20 日窗口和
  2,000 万元门槛；决策分别保存研究成员、新增风险资格、诊断池、稳定原因码和可复算
  内容身份，20 个共同交易日逐日补零只用于流动性资格；
- 行业与财务选择器按历史截止过滤未来归属、公告和修订，严格行业层级不向上回退；
- 核心输入身份绑定准确 `DataSnapshot`、共同日历、U0 决策集、数据集内容哈希、
  行数、日期范围、最大可用时间和封存层级，并拒绝重复数据集名、当前会话与未封存
  日内输入；
- 1.1.0 将共同日历补强为唯一公共 `CoreCommonCalendar`，在快照内保存完整有序
  sessions 并使用统一 `core-common-calendar-v1` 哈希；三包返修不得各建日历身份，
  从而关闭“所有证券同时删一日、各包单测仍通过但联合快照不兼容”的缺口；
- 同次补强把原始因子输出升级为 `core-raw-feature-output-v2`，新增完整计算语义
  `computation_manifest_hash`；当前尚无已发布或持久化的生产
  `CoreInputSnapshot`/原始因子制品，因此这是正式生产前的失败关闭合同升级，不迁移
  旧测试/试制 payload，旧 v1 payload 明确拒绝；
- `CoreFeatureValue` 与权威数据合同一致，完整保存
  `observed / missing / not_applicable`、原始/处理值、填补、指示和诊断字段，所有数值
  必须有限且字段状态严格一致；
- 三包共用两阶段原始公式输出 builder：先对不含 `feature_snapshot_id` 的规范行草稿
  计算内容身份，再注入统一共享 `FeatureSnapshot`；manifest 保存规范特征顺序、逐行
  身份、行数、逐特征覆盖和内容哈希，并显式绑定核心输入、完整包规范、定义注册表
  与完整计算语义哈希；draft、manifest、envelope 均用同一组规范身份函数重算验证，原始阶段不做
  缩尾、填补、标准化或中性化；
- `CoreFeaturePackageSpec` 进一步冻结三包准确 `required_definition_registry_hash`：
  F0 使用第 6 节 24 个 ID 顺序，Alpha158 使用固定 Qlib 158 维顺序，Alpha101 使用
  `alpha101_001` 至 `alpha101_101`；builder、draft、manifest、envelope 都要求实际
  注册表哈希与包内锚点一致，即使伪造方重算全部行、snapshot 和 manifest 身份也失败；
- 三份聚焦单测覆盖新股、北交所、ST、未知、停牌、流动性/覆盖、未来泄漏、
  非 A 股、规格篡改、三态/非有限值、三包共用 envelope、宽度/重复、幂等与内容变化
  负测；身份与 dump 篡改负测独立放在专属测试模块，既有数据语义测试保持原样。
  未修改共享契约、Data、MiniQMT、前端、生产数据或交易代码。
