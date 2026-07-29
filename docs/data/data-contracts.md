# 数据产品与点时正确契约

- 状态：规划基线
- 实现状态：WP-0002B-H4 已发布最小历史主干、公司行为与统一研究价格生产快照

## 数据产品分层

| 层 | 含义 | 可变性 |
| --- | --- | --- |
| 原始层 | 提供方响应、请求与抓取元数据 | 只追加 |
| 标准化层 | 统一身份、单位和可用时间的类型化记录 | 版本化、可重建 |
| 快照层 | 一次请求使用的一组明确数据版本 | 不可变 |
| 特征层 | 绑定快照和定义版本的点时正确派生值 | 不可变 |
| 模型层 | 绑定特征和代码身份的模型或预测 | 不可变 |
| 研究证据层 | 回测、封存回放与候选独立 Research Shadow 事实 | 不可变事件历史 |
| 组合层 | 优化问题、结果和目标持仓 | 不可变事件历史 |
| 执行层 | 订单计划、Local Replay 测试事件与 Broker Paper/Live 事件 | 不可变事件历史 |

“最新”只能是指针，不能成为研究、模型、组合或执行记录的真实身份。

Local Replay 的日度推进只接受一个准确 `DataSnapshot` 中明确列出的交易日历、原始
日线和逐日可交易状态。入口、估值和退出检查点记录快照身份与行情证据哈希；不能查询
`latest`、扫描目录、跨快照补值或把盘后日线描述为实时/Paper 成交。前向证据必须按
类别解释：Research Shadow 记录候选登记后新到达数据上的研究事实；MiniQMT
Paper 才记录券商成交、账户恢复和运营成熟度。两者不得合并或互相补写。

Research Shadow 每个候选至少固定 `strategy_version_id`/`core_policy_version_id`、
`sleeve_id`、周期、登记时间、首个合法决策时点、数据/特征/成本/股票池版本和独立
虚拟账本身份。其现金、持仓、订单、费用、失败和净值不能跨候选共享。

Paper 账户投影至少把每个本系统增量绑定到 `sleeve_id`、准确政策版本、
`order_intent_id`、`managed_lot_id` 和券商订单指纹。内部短线/核心虚拟分仓不改变
MiniQMT 完整账户快照作为唯一券商事实的地位。

## 标准化数据集必备元数据

```text
dataset_name
dataset_version
schema_version
provider
source_endpoint
provider_lineage
request_identity
retrieved_at
market_timezone
date_range
universe
primary_key
availability_rule
units
content_hash
row_count
known_gaps
```

每条观察还必须有市场日期或经济期间以及 `available_at`。如果提供方只有日期，适配器采用保守、书面记录的市场时间规则。

## 初期数据目录

### 证券与交易日历

- 证券主表、上市/退市日期、交易所、板块和名称历史；
- 交易日；
- 可获得的历史 ST、停牌和涨跌停状态；
- 公司行为与复权因子。

这些数据决定某证券在决策时点是否存在、是否可交易。

### 日度市场数据

- 不复权 OHLCV 与成交额；
- 复权因子，以及单独派生的复权价格；
- 换手率、流通/总市值、估值和涨跌停价格；
- ETF OHLCV、成交额、份额/规模；
- 宽基指数与行业指数。

复权收盘价不能覆盖标准化源数据中的原始收盘价。

#### 宽基指数日线

WP-0038 新增 `broad_index_daily`，固定注册表版本
`a-share-broad-index-v1`，首期只包含上证指数、深证成指、创业板指、科创 50、沪深
300 和中证 1000：

```text
BroadIndexDailyObservation
  provider
  source_endpoint
  retrieved_at
  available_at
  schema_version
  source_record_hash
  registry_version
  instrument_id
  instrument_name
  trade_date
  open
  high
  low
  close
  previous_close
  change
  percent_change
  volume_lots
  amount_cny
```

Tushare `index_daily.amount` 的提供方单位为千元，规范化时乘以 1,000 写入
`amount_cny`；`volume_lots` 保留提供方手数口径。日线在交易日 18:00
（Asia/Shanghai）后可用。缺失部分 OHLC、重复 `(instrument_id, trade_date)`、非法
高低价关系或注册表外身份时阻断发布。页面周/月 K 只能从同一
`broad_index_daily` 版本确定性聚合。

### 统一价格图表切片

大盘指数、策略选出的个股、行业内研究股票和 ETF 共用一个只读价格检查器。检查器消费版本化行情，不建立第二个行情真相源。

```text
PriceChartSlice
  chart_slice_id
  instrument_type
  instrument_id
  data_snapshot_id
  bar_dataset_version
  as_of
  interval
  adjustment
  start_trade_date
  end_trade_date
  evidence_cutoff
  bar_count
  content_hash
  known_gaps

PriceChartMarker
  chart_slice_id
  source_type
  source_id
  source_version
  event_trade_date
  available_at
  marker_kind
  label
```

- `instrument_type` 至少区分指数、股票和 ETF；
- 首期提供日/周/月聚合、OHLCV、成交额、MA5 和 MA20，分钟级不在初期范围；
- 周/月 K 必须从同一基础日线版本确定性聚合，并继承相同复权口径和截止时间；
- 指数不显示股票式复权口径；个股和 ETF 必须明确不复权、前复权或后复权；
- 策略标记、目标线和风险线与行情事实分层渲染，并携带各自来源版本；
- 封存回放的 `end_trade_date` 不得晚于 `evidence_cutoff`，浏览器也不得预载或通过缩放暴露未来 K 线；
- 底部双端范围轴只改变客户端可视范围，不创建新行情版本，也不能请求或展示 `evidence_cutoff` 之后的数据；
- 悬浮提示直接读取被十字线选中的真实 Bar，显示交易日期、OHLC、涨跌额/幅、成交量、成交额和启用均线；缺失字段显式标记，不从相邻 Bar 插值；
- 行情陈旧、复权未知、快照不一致或存在关键缺口时失败关闭，不显示演示蜡烛。

### 龙虎榜

主要提供方候选：

- Tushare `top_list`：证券日度龙虎榜事件；
- Tushare `top_inst`：席位或机构买卖明细。

实际起始日期、权限与字段完整性必须在阶段 2 通过提供方接口核验。原始响应只追加保存，因为同一股票/日期可能有多个上榜原因，提供方也可能更正记录。

```text
LhbEvent
  event_id
  trade_date
  ts_code
  reason_code
  reason_text
  close
  pct_change
  turnover_rate
  amount
  list_buy
  list_sell
  list_amount
  net_amount
  net_rate
  amount_rate
  float_value
  available_at
  source_record_hash

LhbSeatDetail
  event_id
  seat_name
  side
  buy
  buy_rate
  sell
  sell_rate
  net_buy
  classification_version
```

席位分类必须版本化，当前对营业部或机构的标签不能静默改写历史特征。

候选特征：

- 净额/流通市值；
- 机构净额/龙虎榜总额；
- 买卖集中度与席位分歧；
- 上榜原因；
- 5/20 个交易日重复出现；
- 事件后衰减与历史同类事件结果。

可用时间规则：龙虎榜属于盘后证据，默认最早只能用于下一可交易时段。

### 股东户数

主要提供方候选：Tushare `stk_holdernumber`。

```text
ShareholderCountObservation
  ts_code
  end_date
  ann_date
  holder_num
  available_at
  source_record_hash
```

点时选择使用 `ann_date`/`available_at`，不能只使用 `end_date`。重述或同一期间多次公告在原始层分别保留。

候选特征：

- 相对上一次披露的变化；
- 按不规则披露间隔折算的变化速度；
- 连续增加/减少；
- 相对同行业、相近市值公司的横截面异常；
- 观察年龄与覆盖置信度。

股东户数是慢速上下文。缺失或陈旧数据继续标记为缺失/陈旧，不伪装成每日新信号。

### REQ-0005 生产事件版本

WP-0008 将 Tushare `top_list`、`top_inst` 和 `stk_holdernumber` 分别发布为
`lhb_event`、`lhb_seat`、`shareholder_count`。三个数据集保留提供方原始空值，不把
缺失金额或比率填成零；每条记录以 `source_record_hash` 去重并保留来源身份。

- 龙虎榜事件和席位的 `available_at` 为交易日 18:00 Asia/Shanghai，只能驱动下一
  交易日及之后的执行；
- 股东户数通常按公告日 18:00 可用；若提供方出现公告日早于报告期末的异常记录，
  `available_at` 保守取两者较晚日期 18:00，并把异常写入数据集缺口；
- `top_inst` 金额单位统一为人民币元；`top_list` 金额保留提供方万元单位并在字段名和
  清单中明确；
- 回放只能读取包含这三个准确版本的 `DataSnapshot`，缺少事件版本时事件策略失败
  关闭，不回退到行情代理。

### REQ-0005 v1.1 连续事件版本

WP-0035 将一次性 2023–2025 事件版本扩展为连续数据产品：

- 日度管线在目标日 20:05 后分别查询 `top_list`、`top_inst` 和
  `stk_holdernumber`，原始响应只追加；
- 三类事件固定同一基础版本，按年度合并并以 `source_record_hash` 去重；同一快照不
  允许出现两个同名事件数据集；
- 目标日事件、行情、交易状态、行业和派生快照全部完成后才切换唯一管线提交；
- 2005–2022 使用显式可恢复长回填，不进入日度关键路径；早期股东户数空窗口是覆盖
  事实，不等于零户数；
- 2026 增量和历史扩展都只产生新版本，不改写 2023–2025 封存证据身份。

`price_limit` 在 2007 年前仍保持未知。WP-0035 的只读探测逐 SSE 开市日查询
`stk_limit`，保存原始响应和标准化分区；任一空响应、重复主键或范围外记录都使结果为
`historical_unavailable`。探测报告不得切换 `price_limit` 或快照指针；只有全部交易日
完整时才标记 `backfill_ready`，实际补齐仍需独立发布步骤。

2026-07-28 真实验收结果：合并快照包含龙虎榜 238,386 行、机构席位 2,534,436 行和
股东户数 435,017 行。龙虎榜首条真实观察在 2008 年，机构席位首条真实观察在 2012 年；
相应早期空年份已写入清单缺口。`stk_limit` 对 2000–2006 全部 1,683 个 SSE 开市日
均返回空，故早期状态继续未知，涨跌停价格仍从 2007-01-04 才可用。

### 财务数据

首期只建设被明确因子使用的小型财务集合：

- ROE 与盈利能力；
- 营收和净利润增长；
- 经营现金流质量；
- 杠杆与利息负担；
- 估值与市值；
- 报告期、公告日、更新标志和可用时间。

银行等特殊行业可以使用独立定义。初期不迁移提供方全部财务报表仓库。

### 周度核心因子数据语义（已批准需求，未实现）

REQ-2026-0007 v2.0.0 未来使用独立 `data_semantics_version` 固定连续研究价与原始执行
事实的映射。该登记不改变当前生产快照：

- OHLC 使用连续研究价格指数；
- VWAP 从原始成交额/成交量构造后缩放到同一研究价格指数；
- 因子收益使用研究收盘价；
- 成交量、成交额、换手、市值、容量、整数手、费用和成交使用原始点时值；
- 前/后复权兼容价只用于审计。

计划的特征值最小结构为：

```text
CoreFeatureValue
  feature_snapshot_id
  instrument_id
  decision_time
  feature_definition_id
  feature_definition_version
  value_raw
  availability_state       # observed / missing / not_applicable
  missing_reason_code
  value_winsorized
  value_standardized
  imputation_source        # none / sw_l1_median / u0_median
  missing_indicator
  not_applicable_indicator
  neutralized_diagnostic
  data_semantics_version
```

数值占位不能覆盖 `availability_state`。`full` 因子顺序、`selected` 冻结清单、模型
输入维数、覆盖统计和去重理由属于 `FeatureSnapshot` 清单；24/158/101 只表示规范
因子值，不包含缺失指示、行业 one-hot 或规模控制。

财务观察还必须保留报告期、累计/单季口径、准确公告或修订时间、修订身份和源记录
哈希。只有公告日期时，从下一沪深共同交易日收盘后可用；修订不回写旧快照。TTM 流量
固定为“本年累计 + 上年全年 − 上年同期累计”，缺期或不可比时失败关闭，不机械年化。

Alpha158 公式固定到 Qlib 提交
`79633dd9506ea689e5400dea0197717b5b3d74b7`；Alpha101 固定到论文 v3 和本地算子注册表。
运行时不得访问 GitHub，实施必须用带输入/输出哈希的本地 golden fixture 验证。

### 行业归属与生命周期

```text
IndustryMembership
  taxonomy
  taxonomy_version
  industry_code
  industry_name
  ts_code
  effective_from
  effective_to
  available_at
  source
```

如果只能取得当前行业归属，它可以服务当前看板，但不能被描述为无生存者偏差的历史行业归属。

WP-0009 将行业基础拆成三个不可变数据集：

- `industry_taxonomy`：`SW2021:L1` 行业代码、名称、提供方代码和发布标记；
- `industry_membership`：证券与一级行业的 `[effective_from, effective_to)` 区间，
  同时保留当前与退出成员；
- `industry_index_daily`：一级行业指数 OHLC、涨跌、估值及提供方原生量额字段。

SW2021 对 2021 年以前的归属是提供方按新版分类的历史回溯，不等同于当时已公开的
分类事实；提供方也未给出成员变更的逐条历史发布日期。两项均进入清单已知缺口。
同一证券同一行业的重叠提供方区间保留来源并作为缺口披露；跨行业重叠会使时点归属
含糊，因此阻断发布。
`sw_daily` 的量、额和市值在权威单位核验前不换算，字段和清单标为
`provider_native_unverified`，不以猜测单位污染研究。提供方极少量高低价与开收价
存在小于 1bp 的舍入差异，原值保留并披露容差；超过 1bp 的异常仍阻断发布。

WP-0026 已实现 `SW2021:L2` 分类、成员和指数数据产品，并要求 31 个 L1 均可
下钻；“电子→半导体”是验收样例而非唯一入口。该规划不得改变现有 L1 数据集身份：

- L2 分类记录父级 L1 身份；
- L2 覆盖、行情和轮动横截面与 L1 分开；
- “半导体”不得加入 31 个 L1 节点或与 L1 混合标准化；
- L2 默认在父 L1 内比较，可显式切换全部 L2；两个集合使用不同基准身份；
- L2 可进入当日有效成分股的轮动、排序和价格检查器，三者绑定同一快照和成员版本；
- 个股层保留全部当日有效成员及其可用 K 线；轮动只消费同一快照内 141 日面板完整
  的成员，显式记录新股、停牌等面板缺口的排除数量和代码，合格成员少于 3 个时阻断，
  不做价格填充；
- UI-PROP-0002 v0.3 已批准并实现；2026-07-28 生产快照发布 31 个 L1 与 134 个
  L2 分类，其中提供方标记的 124 个已发布 L2 均有指数日线。未发布分类保留在分类
  证据中但不进入轮动节点；如果后续快照缺少 L2，页面仍显示
  `sw2021_l2_not_published`。
- 父级内已发布 L2 少于 3 个时，层级视图保持可导航并返回
  `sibling_cross_section_below_three`，但不生成轮动坐标；该缺口不能用父级坐标、
  中心点或“全部 L2”结果静默替代。

WP-0033 在 `IndustryHierarchyView` 的个股层追加同快照证据：

```text
PriceCandle
  trade_date
  open / high / low / close
  volume_lots
  amount_cny

StockFundamentalEvidence
  market_date
  available_at
  latest_close / percent_change / turnover_rate
  price_earnings_ttm / price_book
  total_market_value_cny / circulating_market_value_cny
  amount_cny

StockEvidence
  fundamental                         # 截止日兼容字段
  fundamental_history[]               # 日线近 300 日 + 历史周/月末点
  shareholder_concentration           # 截止日兼容字段
  shareholder_concentration_history[] # 按实际 available_at 的公告序列

ShareholderConcentrationEvidence
  status
  announced_on / reporting_period / available_at
  holder_count / previous_holder_count / change_rate
  direction / consecutive_periods / observation_age_days
  known_gaps
```

响应分别提供日、周、月 `PriceCandle`。周/月先按 `as_of` 裁剪日线，再只聚合已完成
周期；技术指标在浏览器按当前周期重算。悬浮收益的终点始终是同响应日线的最后已完成
交易日，不是未完成周/月，也不读取未来 Bar。基本面与股东户数遵守各自
`available_at`；缺少 `shareholder_count` 时返回 `shareholder_count_not_in_snapshot`，
不得从另一快照补齐。蜡烛图悬浮日期只在浏览器内选择 `market_date <= hover_date`
且 `available_at <= hover_date` 的最近观察；公告前显示不可用，hover 不产生请求。

WP-0025 v1.1 已实现日度增量发布链：

```text
trade_calendar
+ industry_index_daily (31 L1 + 全部已发布 L2)
+ daily_market / adjustment_factor / daily_basic / price_limit / suspension_event
+ adjusted_market / daily_tradability
→ DataSnapshot
→ MarketRotationSnapshot
→ 唯一 daily-pipeline commit 指针
```

页面和功能模块只读消费该链；提供方未完成或发布中断时保留上一完整指针并显式标记
陈旧或阻断，不允许由页面请求隐式拉取和混合版本。

`DailyPipelineStatus` 记录目标交易日、基础快照、运行状态、L1/L2 预期及实际覆盖、当前
步骤、阻断和恢复动作。`DailyPipelineCommit` 同时绑定准确 `DataSnapshot` 与
`MarketRotationSnapshot`；只有该提交存在，消费者才把整组产物视为共同完成。每次
提交同时保留按内容寻址的不可变制品；历史恢复按
`base_snapshot_id + target_date` 的准确数据运行身份取回提交，禁止读取全局最新日期
或当前提交指针代替本次输入。旧版本只保存完成状态时，可以由状态中的准确快照、
轮动与完成时间重建同一提交身份。

日度运行冻结基础快照，但最终激活必须对 `current/data-snapshot.json` 做带文件锁的
比较并交换：当前身份仍等于冻结基础时才可切换。若 ETF 等独立发布在日度运行期间已
推进当前快照，旧运行以 `concurrent_snapshot_advanced` 阻断，并从最新快照重新启动，
不得恢复旧基线覆盖新数据集。已发布的不可变数据集可通过显式修复命令重新组合进一个
新快照；修复不重新抓取提供方、不改写旧快照，也不触碰券商。

WP-0029 只接受上述提交，并按身份生成：

```text
FeatureSnapshot → PredictionBatch
→ OptimizationProblem / OptimizationResult
→ PortfolioTarget → OrderPlan (Local Replay test)
→ Local Replay / Paper 就绪预检
```

决策链制品和状态固定记录 `paper_dispatch_state=disabled`、
`broker_connection_attempts=0`、`broker_write_attempts=0` 和
`broker_actions_allowed=false`，不包含活动 Paper 周期或券商执行事件。

```text
IndustryLifecycleProjection
  status
  data_snapshot_id
  as_of
  evidence_cutoff
  taxonomy_version
  method_version
  industries[]
    industry_code
    industry_name
    stage
    confidence
    strong_participation
    low_participation
    strong_change_5d
    low_change_5d
    strong_peak_20d
    strong_drawdown_20d
    amount_share_20d
    eligible_member_count
    valid_member_count
    coverage_ratio
    recently_transitioned
    trajectory[]
    known_gaps[]
  known_gaps[]
```

旧 AstraMind 的生命周期公式与 Fixture 是复用候选。旧项目“56 行业”只是某个注册表版本，不是领域不变量。

WP-0040 已将 `lifecycle-structure-v1.0.0` 冻结为首个结构方法：
`strong_participation` 是横轴 `S`，`low_participation` 是纵轴 `L`，
`amount_share_20d` 表示气泡面积。坐标、阶段、置信度和行业索引绑定同一个
`DataSnapshot`；后续研究排序也必须复用该身份。覆盖不足的行业保留身份和缺口原因，
不放到坐标原点。该投影可由快照重建，不是第二份数据真相。

### 行业内研究排序

```text
IndustryResearchRankingSnapshot
  ranking_snapshot_id
  data_snapshot_id
  lifecycle_snapshot_id
  as_of
  taxonomy
  taxonomy_version
  industry_code
  scoring_definition_version
  member_count
  covered_member_count
  content_hash
  known_gaps

IndustryResearchRow
  ranking_snapshot_id
  ts_code
  membership_effective_as_of
  overall_priority
  event_sentiment_score
  technical_volume_score
  fundamental_score
  risk_score
  reversal_repair_score
  coverage
  research_label
  evidence_cutoff
```

- 成分股归属按 `as_of` 选择，不能用当前行业归属静默重写历史排序；
- 所有分项和综合分绑定 `scoring_definition_version`，综合分不能只暴露不可解释的 AI 结果；
- `research_label` 在覆盖达标时只使用“优先研究”“积极关注”“中性观察”；覆盖低于
  60% 时使用“数据不足”，它不是投资决定、组合目标或订单；
- 排序表和所选股票 `PriceChartSlice` 必须使用同一 `data_snapshot_id`、`as_of`、分类版本和证据截止时间；
- 覆盖不足的股票显示缺失原因，不用零分填补后继续排名。

### 行业资金相对轮动

```text
MarketRotationSnapshot
  rotation_snapshot_id
  data_snapshot_id
  as_of
  benchmark_id
  benchmark_definition_version
  formula_version
  taxonomy
  taxonomy_version
  industry_count
  covered_industry_count
  date_range
  content_hash
  known_gaps

IndustryRotationPoint
  industry_code
  trade_date
  relative_trend
  relative_momentum
  raw_z_trend
  raw_z_momentum
  display_transform_version
  quadrant
  coverage
  constituent_count
  trail_direction
  overflow

IndustryRotationEvent
  industry_code
  from_quadrant
  to_quadrant
  first_cross_date
  confirmed_date
  formula_version
  rotation_snapshot_id
```

轮动快照必须绑定同一个数据快照、基准、公式和行业注册表。行业数量来自注册表，不写死 56。任何日期覆盖不足时失败关闭，不用中心点、前值或演示数据补齐。

WP-0010 已冻结正式公式 `rotation-index-ew-v1.0.0`：

- 31 个 `SW2021:L1` 行业指数同日对数收益等权平均作为基准；
- 相对累计状态的 20/60 日 EMA 差作为趋势，趋势 5 日差作为动量；
- 每日横截面使用中位数/MAD 稳健标准化，退化时使用总体标准差，仍为零则阻断；
- 坐标为 `100 + 5 × clip(z, -3, 3)`，中性带 `±0.25`，连续 2 日确认跃迁；
- 读取 141 个交易日，预热 140 日，只发布最近 60 日；
- 31 个指数要求 100% 面板覆盖，每个输出日每行业至少 3 个有效成分。

REQ-2026-0002 v1.3.0 保持上述逻辑公式、象限和事件不变，规划追加硬截断前
`raw_z_trend/raw_z_momentum`，并冻结显示层
`rotation-display-tanh-v1.0.0`：

```text
display = 100 + 14 × tanh(raw_z / 2.5)
```

显示值只用于画布，不反写逻辑坐标、象限、事件或旧快照。声明 tanh 版本却缺少 raw_z
时必须阻断；没有新字段的旧快照继续使用其原始映射并明确显示旧版本。

`MarketRotationSnapshot` 采用规范 JSON 和 `sha256:` 内容身份；当前指针原子替换，
读取时复验哈希。结构事件嵌套于所属快照，快照身份由外层
`rotation_snapshot_id` 唯一给出，避免在哈希内容中形成自引用。该数据产品衡量价格
相对强弱，`known_gaps` 必须包含
`price_relative_strength_proxy_not_direct_capital_flow`。

### ETF 方向

行业到 ETF 的映射随时间和版本变化：

```text
EtfDirection
  direction_id
  industry_exposures
  etf_code
  effective_from
  effective_to
  mapping_version
  evidence_source
```

ETF 候选必须独立通过上市时间、流动性、成交额、价差/代理、跟踪、停牌和可交易性检查。静态映射本身不是价格确认。

WP-0043 首版数据基础固定发布四个数据集：

| 数据集 | 主键 | 核心内容 | 可用时间 |
| --- | --- | --- | --- |
| `etf_master` | `instrument_id` | 名称、类型、基准、上市/退市日与状态 | 提供方检索时点；上市日不得替代检索时点 |
| `etf_daily` | `instrument_id, trade_date` | OHLC、昨收、涨跌、成交量与人民币成交额 | 交易日 18:00 Asia/Shanghai |
| `etf_share` | `instrument_id, trade_date` | 规范为“份”的基金份额 | 提供方检索时点；首版不假设历史发布日期 |
| `etf_industry_mapping` | `industry_code, etf_code, effective_from` | SW2021 L1、ETF、语义层级与映射版本 | `effective_from` 当日 18:00 Asia/Shanghai |

首版映射 `sw2021-l1-etf-mapping-v1.0.0` 从 2026-07-29 起有效；更早的 ETF
价格只能预热，不能据此声称当时已知该行业映射。语义层级为 `exact`、
`subindustry`、`composite_proxy`、`theme_context` 或 `unavailable`，只有 `exact`
可以进入基础资格。

`EtfFoundationQualification` 必须绑定 `data_snapshot_id`、`evidence_cutoff` 和
`mapping_version`。基础门槛为至少 252 个已完成交易日、20 日成交额中位数不低于
2,000 万元、最新份额乘收盘价不低于 1 亿元且证据不陈旧。其
`strategy_gate_ready` 固定为 `false`；价差、跟踪误差、停牌/可交易性、成本和
样本外证据缺失时不得提升为 ETF 策略候选。

WP-0044 的只读 `EtfRotationProjection` 绑定同一个 `data_snapshot_id`、
`evidence_cutoff`、映射版本和 `etf-rotation-research-v1.0.0`。首版综合分为：

```text
0.35 × lifecycle + 0.30 × relative_strength
+ 0.20 × price_structure + 0.15 × liquidity
```

候选额外要求 Corwin–Schultz 20 日 OHLC 价差代理不高于 35 bp，以及相对映射申万
L1 指数的 60 日年化跟踪偏离代理不高于 12%。两者分别标记为价格代理和行业暴露
代理，不得称为真实 bid/ask 或基金官方基准跟踪误差。`EtfTargetDraft` 最多两只、
单只 30%、总暴露 60%，允许现金；它不是公共 `PortfolioTarget` 或 `OrderPlan`。
映射尚未点时可用、历史不足或数据陈旧时，回放和目标失败关闭，不补造绩效。

### 市场研究学习模型

WP-0050 为行业热力、相对轮动、生命周期、行业内研究顺序和 ETF 轮动增加独立的只读
模型身份。训练产物由 Strategy Research 拥有，Market Regime 只能通过公共契约消费；
它们不得替代 Data 的观察或快照真相。

```text
MarketModelManifest
  manifest_id
  model_family
  method_version
  target_definition_version
  data_snapshot_id
  feature_snapshot_id
  training_window
  maturity_cutoff
  feature_names
  estimator
  hyperparameters
  random_seed
  code_identity
  dependency_versions
  artifact_hash
  created_at

ModelValidationSummary
  validation_id
  manifest_id
  validation_window
  metric_name
  candidate_value
  reference_value
  bootstrap_lower_bound
  subperiods_supporting
  subperiods_total
  coverage_not_worse
  risk_not_worse
  turnover_not_worse
  cost_not_worse
  decision
  reason_codes

MarketModelEvidenceBundle
  evidence_bundle_id
  manifest_id
  development_window
  sealed_window
  audit_window
  validation_summaries
  data_gate_states
  evidence_state
  content_hash
  created_at

ModelActivation
  activation_id
  model_family
  active_method_version
  active_manifest_id
  evidence_bundle_id
  state
  fallback_method_version
  reason_codes
  effective_at
  broker_actions_allowed = false

ModelPredictionContext
  model_family
  method_version
  manifest_id
  prediction_batch_id
  data_snapshot_id
  feature_snapshot_id
  as_of
  horizon_sessions
  evidence_state
  activation_state
  fallback_reason_codes

MarketPredictionBatch
  prediction_batch_id
  model_family
  manifest_id
  data_snapshot_id
  feature_snapshot_id
  as_of
  horizons
  regressions[] / classifications[]  # 两者严格二选一
  evidence_state
  content_hash
  broker_actions_allowed = false
```

每个预测批次还必须绑定标签成熟截止、训练截止、模型/特征内容哈希和原始结构方法
版本。`unvalidated`、`fallback_v1`、`blocked` 和 `corrupt` 是不同状态；未知状态
不能写成已验证。

SW2021 在 2021 年以前的成员记录带
`reconstructed_not_then_known` 数据门，不能进入封存 OOS 或模型比较。ETF 的真实
官方证据和 L1 价差必须分开保存原始提供方记录与规范观察：

```text
EtfOfficialBenchmarkObservation
  provider / source_endpoint / retrieved_at / available_at
  instrument_id
  benchmark_code / benchmark_name
  effective_from
  historical_availability_known
  evidence_kind
  source_record_hash / schema_version

EtfNavObservation
  provider / source_endpoint / retrieved_at / available_at
  instrument_id / nav_date / announced_on
  unit_nav / accumulated_nav / adjusted_nav
  source_record_hash / schema_version

OfficialIndexDailyObservation
  provider / source_endpoint / retrieved_at / available_at
  index_code / trade_date
  open / high / low / close / previous_close
  change / percent_change / volume / amount
  source_record_hash / schema_version
```

当前 `etf_basic` 查询只证明检索时的官方跟踪关系；在取得历史公告或版本证据前，
`historical_availability_known=false`，不能倒灌为 2024—2025 封存期已知事实。
NAV 以 `ann_date` 18:00 为可用时点；缺失公告日时失败关闭。指数日线的提供方 0 值
OHLC 显式保存为缺失，不用收盘价或其他日期填造。

真实 L1 价差观察继续分开保存原始报价和规范分钟统计：

```text
EtfSpreadMinuteObservation
  provider
  feed_session_id
  instrument_id
  market_date
  minute
  first_market_time
  last_market_time
  quote_count
  valid_quote_count
  quoted_spread_bps_median
  quoted_spread_bps_p90
  available_at
  source_content_hash
  schema_version
```

真实价差只从采集登记后前向积累，不用 OHLC 代理补历史。连续 60 个交易日、交易日
覆盖、分钟覆盖、中位数和 P90 门禁必须进入单独的数据门证据；未满足时 ETF v2
保持阻断。

### MiniQMT 行情、资料与本地缓存

东莞证券 MiniQMT 是实时行情和本地资料的已验证/候选提供方之一：

- 用户已验证本地行情 RPC 的 L1 全推；
- `subscribe_quote`、`get_full_tick` 和 `get_l2_quote` 已由本机 API 暴露；
- K 线、Tick、历史下载、交易日历、合约、板块/行业/指数权重、财务、复权因子、
  ETF 和可转债资料按数据集逐项核验；
- L2 是否有实际数据取决于券商权限，默认不得宣称可用。

提供方中立采集使用以下薄腰契约：

```text
CanonicalDatasetRequest
  dataset_name
  as_of
  start_date / end_date
  universe
  fields
  allow_empty
  frequency
  adjustment
  point_in_time_policy

DatasetSourceRoute
  dataset_name
  providers
  provider_lineage
  adapter_versions
  timeout_seconds
  primary_key
  required_fields
  quality_gate_version

ProviderBatch
  provider_id
  provider_version
  native_interface
  request_identity
  retrieved_at
  rows
  raw_payload
  completeness
  known_gaps
  latency_breakdown
```

`allow_empty` 默认关闭，只能用于语义上允许零行的已冻结子请求，例如
`security_master` 的暂停上市状态切片；它不改变数据集路由的默认失败关闭策略，也
不能让在市或退市证券主表空结果通过。

每次管线运行开始时冻结完整路由。主源超时、空响应、缺字段、覆盖不足、重复主键或
校验失败时，路由层保留失败原始证据并丢弃其规范化结果，再让当前提供方时期允许的
回退源完整重取该数据集。默认同一数据集版本只有一个实际提供方；明确批准的日期切源
例外必须在路由和 `DatasetManifest.provider_lineage` 中记录非重叠时期，并保持逐行
来源。单个请求不得跨越切源日，同一交易日不得混用提供方。

`daily_market` 与 `broad_index_daily` 的首个日期切源固定为：Tushare
`effective_to=2026-07-28`，MiniQMT `effective_from=2026-07-29` 且结束日开放。
2026-07-28 及以前不重抓 MiniQMT 历史；2026-07-29 及以后不回退到 Tushare。
`daily_market` 的当日证券集合至少覆盖同日 `daily_basic` 证券集合；MiniQMT 本地
缓存只返回部分证券时必须失效当日暂存并重取，不能仅凭提供方字段正确而发布。

```text
ProviderCapabilityProbe
  probe_id
  provider
  gateway_version
  client_version
  probed_at
  account_modes
  interface_name
  interface_present
  entitlement_available
  data_available
  observed_fields
  known_gaps

MarketFeedSession
  feed_session_id
  provider
  gateway_version
  market_level
  entitlement_identity
  connected_at
  disconnected_at
  subscriptions
  reconnect_count
  first_market_time
  last_market_time
  last_received_at
  known_gaps

RealtimeMarketObservation
  feed_session_id
  instrument_id
  observation_kind
  market_time
  received_at
  provider_sequence
  payload_schema_version
  source_record_hash
```

WP-0002A 已将能力证据实现为冻结的 `ProbeReport` 与 `ProviderCapability`：

- 状态区分 `available`、`unavailable`、`permission_denied`、`empty`、`stale`、
  `error` 和 `not_probed`；
- 原始响应由 `RawRecordEnvelope` 包装并只追加保存；
- Token、Windows 用户路径和提供方错误正文不进入报告；
- `make provider-probe` 是显式联网命令，默认质量门只使用合成替身。

- `market_time` 与 `received_at` 分开；提供方没有序列时不得伪造序列；
- 订阅、退订、断线、重连和缺口必须进入会话证据；
- 全推消息先保存提供方原始记录，再形成标准化观察或不可变微批；
- MiniQMT 本地缓存是提供方缓存，不是 `DataSnapshot` 身份或第二套数据真相；
- Tushare 与 MiniQMT 混合时，快照清单按数据集记录提供方、版本、时间规则和哈希；
- 来源冲突必须输出差异和选源规则版本，不能静默以前值或“最新值”覆盖；
- L2 权限或连续性不足时失败关闭，并明确保留 L1 状态。

MiniQMT 财务、股东和当前资料分别发布为独立数据集。财务事实采用长表，显式记录
报告期、累计/单季口径、币种、单位、公告时间、保守 `available_at` 和修订身份；
修订产生新版本，不回写旧快照。银行等特殊行业允许 `not_applicable`。十大股东和
十大流通股东按公告时间进入点时快照，不能塞入 `daily_basic`。

## 不可变制品物理发布

内容寻址目录中的 Parquet、JSON、模型或证据文件不得与后续仍会更新的工作文件共享
inode。禁止使用硬链接把可变工作文件发布为不可变制品。

发布器必须在原子切换前后复核：

- 每个制品的字节 SHA-256；
- 行数与主键唯一性；
- 最小/最大市场日期和可用时间；
- 清单声明的内容哈希、日期范围与制品实际内容。

任一复核失败时，当前数据集和 `DataSnapshot` 指针保持不变。已发布制品发生漂移时，
旧身份保留审计但暂停用于正式训练、封存回放和晋级证据；恢复只能发布新版本并重组
新快照，不能修改旧清单。ADR-0013 与 WP-0057 是该规则的架构决定和修复工作包。

## 快照清单

`DataSnapshot` 清单记录准确组件版本：

```yaml
snapshot_id: sha256:...
as_of: 2026-07-24T15:30:00+08:00
datasets:
  daily_market: sha256:...
  security_master: sha256:...
  trade_calendar: sha256:...
  lhb: sha256:...
  shareholder_count: sha256:...
  industry_membership: sha256:...
known_gaps: []
created_at: ...
code_identity: ...
```

WP-0002A 已实现 `DatasetManifest`、内容寻址发布、原子当前指针、SQLite/WAL 台账、
确定性 `DataSnapshotBuilder` 和只允许清单内版本化 Parquet 的 DuckDB 查询适配器。
能力探测响应只形成证据，不冒充生产数据。

WP-0002B 已发布真实生产快照。四类标准化观察均携带提供方、端点、摄入时间、
可用时间、Schema 版本和源记录哈希；日线保留原始不复权价格，复权因子独立成表。
WP-0002B-H1 已将日线和复权因子扩展到 2000-01-04 至 2026-07-24。历史行情的
`available_at` 为交易日 18:00（Asia/Shanghai），因此只能用于盘后判断或后续执行。
旧 Silver 原始响应仍由旧系统持有，Mini 保存正式发布身份和原始响应哈希，并明确
记录 `legacy_raw_payloads_external`。任何日线缺少复权因子继续阻断发布。

WP-0002B-H2 新增三类标准化数据：

- `daily_basic`：收盘价、换手率、估值、股本和市值；估值字段允许按提供方定义为空，
  股本单位为万股，市值单位为万元，`available_at` 为交易日 18:00；
- `price_limit`：昨收、涨停价、跌停价与 `limit_prices_usable`，从 2007-01-04
  开始，`available_at` 为交易日 08:40；
- `suspension_event`：停牌 `S` 与复牌 `R` 事件，同一证券同日可以有多个不同事件，
  `available_at` 保守设为交易日 18:00。

覆盖报告显式记录日线与每日指标/涨跌停的双向缺口。`limit_prices_usable = false`
的记录不能参与订单可行性判断。

WP-0002B-H3 新增：

- `security_name_history`：名称有效区间、提供方结束日、可空公告日、变更原因、历史
  `risk_status` 与特别处理标记；有公告日时按公告日 18:00 可用，提供方未给公告日时
  不伪造历史可用时间，而以本次实际获取时间作为 `available_at`；
- `daily_tradability`：上市证券逐开市日的名称/ST 证据、研究资格、Bar/停复牌/
  涨跌停状态，以及买卖两侧可交易状态。

名称区间缺失时为 `unknown`，不能用当前名称倒灌。没有 Bar 不能仅凭“无停牌事件”
判为可交易；只有整日停牌且无同日复牌证据才标记 `suspended`。缺失或不可用的
涨跌停价也必须失败关闭。两类投影均按交易日 18:00 作为盘后证据。完整公司行为和
BSE 独立日历仍是缺口。

WP-0002B-H4 新增：

- `corporate_action`：分红送转的版本化提供方记录，公告日缺失时
  `availability_known=false`，不能进入点时研究；实施公告更新按公告日与实施公告日
  两者较晚者进入可用集，不能把后来获知的实施状态倒灌到初始预案日；
- `adjusted_market`：原始 OHLC、复权因子、快照终端因子、标准前/后复权兼容价、
  连续研究价格指数，以及因子收益与公司行为解释证据。

原始 OHLC 是唯一成交价格。`forward_adjusted_*` 和 `backward_adjusted_*` 绑定
不可变快照，仅用于兼容与审计；默认研究路径使用 `research_*_index`。该指数以首个
可见 Bar 为 1，按提供方日收益累计，长期停牌跨年度时沿用最近锚点。配股和其他非
`dividend` 公司行为仍是显式缺口。

WP-0025 v1.3 将 `security_master`、`security_name_history`、`corporate_action`、
`industry_taxonomy` 和 `industry_membership` 纳入同一个日度原子提交。证券主表与
SW2021 L1/L2 分类/成员每日按提供方完整视图对账；名称历史由当日证券主表与上一
快照最新名称逐证券比较，对新增或名称/ST 变化的证券按代码拉取完整名称链并合并；
公司行动滚动回看最近 8 个自然日的公告日和实施公告日并与已有历史去重合并。五类
数据任一请求达到提供方上限、身份重叠或失败时，不切换 DataSnapshot 当前指针。

## MiniQMT L1 实时微批

WP-0002C 新增实时行情内部契约：

- `FeedSessionReport`：提供方、客户端版本、上海市场日期、市场、订阅起止、消息数、
  重复数、断线数与已知缺口；
- `RealtimeQuoteObservation`：证券、市场毫秒时间、接收时间、L1 价量字段和原始内容
  哈希；
- `QuoteMicroBatch`：会话、顺序、时间窗、原始/规范化内容哈希和行数。

原始全推与规范化观察分开压缩、只追加保存。相同会话/批次身份内容不一致时阻断。
MiniQMT 全推是当前观察输入，不会改写生产 `DataSnapshot`，也不是第二个历史真相源。

WP-0041 将 MiniQMT 行情接入改为 Windows Python 3.11 常驻只读桥。桥只导入
`xtquant.xtdata`，通过带请求身份的 NDJSON 长连接传递查询、行情事件、心跳和错误；
客户端版本、行情端口和本机客户端指纹固定进入会话身份。断线重启必须创建新会话。

原始 L1 与逐条规范化观察按上海交易日、会话和微批只追加保留五个交易日；只有
一分钟聚合分区和哈希验证成功后才能清理，异常会话带保留锁。会话清单、微批清单、
缺口、内容哈希和删除台账永久保留。全 A 股长期保存一分钟 OHLCV/成交额；六个宽基、
市场广度和行业热力的一秒结果只存在于可重建的当前投影，不建立长期一秒分区。
当前投影按一秒节奏发布，服务端通过 SSE 推送；十秒无有效更新标记 `stale`，连接
中断标记 `disconnected`，闭市等待不伪报连接故障。

订阅建立后的首张全市场快照只用于设置累计成交量/成交额基线；只有后续量额出现
正增量才创建分钟 Bar，停牌、隔夜或无成交快照不得伪造成零成交 K 线。

WP-0046 增加证券级当前投影：`RealtimeInstrumentQuote` 保存证券名称/类型、行业、
最后价、涨跌、累计量额、MiniQMT 状态代码和五档；当日 `price_limit` 点时记录存在时
附涨跌停价，不存在时保持空值并登记缺口，不按板块规则猜测。`RealtimeMinuteBar`
继续只追加进入一分钟分区，形成中的最后一分钟只存在当前投影并以同一分钟原位替换。
自选清单属于本地观察配置，不进入 `DataSnapshot`、策略、组合或订单。

2026-07-29 的 WP-0047 运营审计发现，本地 `aggregates/1m` 只有日期目录而没有实际
一分钟聚合文件；现有收盘后累计快照不能反推日内路径。因此“全 A 股长期保存一分钟
OHLCV/成交额”仍是有效目标契约，但在交易时段暖启动、持续增量聚合、跨重启去重和
内容哈希验证通过前，不得把它标记为已完成能力，也不得据此计算多分钟 MA/MACD。
原始/规范化微批仍保留，不能用零成交 Bar 填补这一缺口。

`IndustryLifecycleIntradayProjection` 以最近完成日为锚，把当前会话价格按完成日调整
比例映射到研究价格索引，再以 `lifecycle-intraday-overlay-v1.0.0` 重算临时 S/L；
`intraday-rotation-overlay-v1.0.0` 只生成完成日锚点到当前行业横截面端点。两者均不
保存秒级轨迹、不改变正式阶段/象限，也不进入历史播放。

WP-0022 v1.1 的 Paper 金丝雀行情读取仍使用相同的 `market_time`/`received_at` 语义：
Windows runner 最多等待8秒取得一条年龄不超过3秒的新 tick，领域与提交校验继续固定
3秒阈值。等待期耗尽只形成 `canary_quote_stale` 阻断，不把陈旧缓存发布为提案。

Paper Windows runner 另保存内部 `PaperRunnerDiagnostic`：runner 名称、观察时间、
退出码、稳定 outcome，以及脱敏且最多32,000字符的 stdout/stderr。账户选择器、密钥、
Windows/WSL 用户目录和私有路径不得进入记录；诊断只用于本地排障，不是行情观察、
账户快照或订单事实。

## 多时标行情、当前投影与候选级日内研究

REQ-2026-0004 v2.3.0 和 ADR-0010 冻结下列规划契约；该节是已批准但尚未授权实施的
数据语义，不表示相应数据已经通过真实覆盖验收。

行情数据分为三个不能互相冒充的层次：

1. **当前会话投影**：由追加式实时微批合并的可刷新视图，绑定一个
   `MarketFeedSession` 和最后完成日参考快照；服务盘中页面、风险预检和临时诊断；
2. **不可变实时微批**：保存原始与规范观察、市场时间、接收时间、序号、会话、缺口
   和内容哈希，是当前投影的重建来源；
3. **会话封存日内数据集**：在声明截止后完成覆盖、顺序、交易状态、单位、企业行为和
   来源校验的分钟/Tick 数据集，只有它可以作为 `DataSnapshot` 组件进入研究。

当前会话投影不得被命名为“今日 `DataSnapshot`”或直接成为特征输入。收盘后状态从
`sealing` 进入 `reconciled` 或 `blocked`；没有通过封存与日线对账时，上一完成日
指针保持不变。

候选级日内请求是一个 `CanonicalDatasetRequest` 的受限用法，至少固定：

- 上游 `CoarseScreeningBatch` 身份及其先于日内取值冻结的候选全集；
- 证据截止时间、市场日期、频率、字段、回看窗口、交易时段、复权与单位；
- 提供方路由、权限、超时、覆盖/缺口和质量策略；
- 请求配方版本、幂等键和预期候选数量。

首个短线配方由 REQ-2026-0005 v1.4.0 固定为 Top 20、最近 20 个完整交易日一分钟
数据和最近 3 个完整交易日 Tick/L1。Data 必须请求完整 Top 20；提供方传输缺页先按
整数据集回退处理，合法停牌或无成交保留真实状态。任何候选失败都必须进入覆盖证据，
不得以第 21 名或人工关注标的替换。

每次请求分别保存原始响应、规范化数据集、候选覆盖、来源选择证据和内容身份。相同
参数重复执行时幂等复用；内容变化发布新版本和差异，不覆盖已被策略引用的旧版本。

历史两阶段研究先逐决策日重放日频粗筛，再请求该日冻结候选在证据截止前的数据。
这形成的是粗筛条件样本，不能宣称为全市场分钟/Tick 因子面板。人工关注补拉可以共享
Data 适配器和缓存，但使用独立诊断身份，不能进入策略净值、Research Shadow 或晋级。

## MiniQMT 只读账户与对账

WP-0011 在 Trading Execution 上下文新增 `AccountSnapshot` 与
`ReconciliationReport`。账户快照明确记录模拟盘或实盘模式、查询时点、脱敏账户
指纹、资金、持仓、当日委托和当日成交；账户、委托和成交原始身份只转换为本地 HMAC
指纹，完整标识与 Windows 路径不进入契约、日志或 SQLite。

资产、持仓、委托和成交由四个有独立超时的只读进程顺序查询。因为 MiniQMT 不提供
跨查询原子快照，成功快照固定声明 `non_atomic_sequential_account_queries` 缺口；
任一查询失败时不发布部分快照。历史 Local Replay 账本不被券商事实覆盖，也不得成为
Paper 回退账户；对账差异只生成不可变报告并保持 `broker_actions_allowed=false`。
证据按内容寻址只追加写入
Git 忽略的 `var/control/`，SQLite/WAL 仅索引脱敏身份和发布状态。

## 初期质量门

- 统一证券编码与交易所校验；
- 标准化主键唯一，并保留原始重复审计；
- 交易日历完整；
- OHLC 一致，成交额/成交量规则合理；
- 复权因子连续；
- 上市、ST、停牌和涨跌停状态一致；
- 消费时点不得早于任何观察的 `available_at`；
- 按日期、证券、行业和数据集输出覆盖报告；
- 相同输入重建时内容哈希稳定；
- 提供方限流、分页、部分响应和恢复状态可见。

## 密钥

Tushare Token、券商凭证和账户标识通过本地环境或 Git 排除的密钥文件提供。日志和 Fixture 必须脱敏。
