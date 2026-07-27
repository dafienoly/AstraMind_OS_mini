# AstraMind OS Mini 新会话开发交接

- 交接日期：2026-07-27
- 本地仓库：`/home/ly/work/AstraMind_OS_mini`
- GitHub：`https://github.com/dafienoly/AstraMind_OS_mini`
- 当前分支：`main`
- 当前阶段：WP-0001 至 WP-0006 的首个本地基线已建立；封存证据与持续 Shadow 待继续
- 本文用途：帮助新会话从现有基线继续开发，不替代需求、ADR、数据契约、UI 提案或实施计划

## 一、开始工作前必须先确认的事实

1. 当前仓库还没有首个 Git 提交，`HEAD` 不存在。
2. 当前所有规划和 WP-0001 文件仍为未跟踪文件，尚无可用于比较的 Git 基线。
3. 已存在锁定工具链、公共契约、健康 API、非产品开发诊断页、双提供方能力证据、
   不可变存储，以及 WP-0002B 的首个真实生产 `DataSnapshot`。
4. 本仓库已执行 Tushare/MiniQMT 只读探测和一次获授权的 MiniQMT L1 全推有界采集；
   已实现纯本地 Shadow，但未执行提交、推送、账户读取、Paper、Live 或真实资金动作。
5. 用户已确认本机东莞证券 MiniQMT 可读取实盘/模拟盘账户，并可通过本地行情 RPC
   接收 L1 全推；本机 API 暴露了行情、账户、委托和撤单接口。
6. 开发前建议由用户明确授权建立初始规划基线提交；在获得指令前，不得自动提交或推送。
7. 能力已打通不等于授权本仓库读取真实账户、Paper/Live 下单、首笔订单或真实资金操作。

## 二、新会话必读顺序

按以下顺序读取，不要只依赖本文摘要：

1. [`AGENTS.md`](./AGENTS.md)
2. [`docs/README.md`](./docs/README.md)
3. [`CONTEXT-MAP.md`](./CONTEXT-MAP.md)
4. 受影响上下文的 `docs/contexts/**/CONTEXT.md`
5. [`docs/product/product-baseline.md`](./docs/product/product-baseline.md)
6. [`docs/requirements/README.md`](./docs/requirements/README.md)及相关需求
7. [`docs/data/data-contracts.md`](./docs/data/data-contracts.md)
8. [`docs/ui/interface-inventory.md`](./docs/ui/interface-inventory.md)
9. [`docs/ui/visual-direction.md`](./docs/ui/visual-direction.md)
10. [`docs/planning/phased-implementation-plan.md`](./docs/planning/phased-implementation-plan.md)
11. [`docs/development/vibe-coding.md`](./docs/development/vibe-coding.md)
12. [`docs/development/work-package-template.md`](./docs/development/work-package-template.md)

开始任何代码修改前，先写清本次工作包的目标、非目标、允许文件、影响契约、验收检查和受保护边界。

## 三、最终产品目标

建立一套本地优先、单用户、清楚易懂的 A 股量化交易工作台，以尽可能短的路径完成：

```text
可信数据
  → 可重复策略证据
  → 目标组合
  → 风险与常设授权判断
  → 订单计划
  → 本地 Shadow
  → 单独授权后的 MiniQMT
  → 有限真实执行
```

系统不复制旧 AstraMind 的机构级身份、发布、Formal/Preview、长期观察和多层审批机器。人工只处理超授权、失败和异常。

## 四、已经冻结的产品决策

| 主题 | 已确认方向 |
| --- | --- |
| 首条主线 | 先跑通个股，再建设 ETF 实盘 |
| 短线资金 | 5 万元，常态持有 1–2 只 |
| 长线资金 | 10 万元，约 5 只，周度评估调仓 |
| 短线逻辑 | 事件/关注、动量/突破、反转/量价等多逻辑并行竞争 |
| 策略晋级 | 可以基于封存证据和可见 Shadow 诊断手动晋级 |
| Shadow | MiniQMT 前必须本地跑通，但不设置固定 20 天等待期 |
| 回测区间 | 数据允许时开发截至 2022；2023–2025 为不可见封存回放；2026 为当前观察 |
| 长线模型 | 科技、周期、传统经济允许单独建模；全市场模型作为回退 |
| 机器学习 | 梯度提升为强基线，PyTorch/ROCm 行业专家或多任务模型为挑战者 |
| 强化学习 | 后置到受限仓位分配或执行研究，不直接控制整个账户 |
| 优化器 | 首期稳健受约束权重；公共接口允许后续复杂优化器 |
| 人工审批 | 常设授权内不逐笔审批，异常在工作流原位衔接 |
| 一级导航 | 今日、市场、策略竞技场、组合、系统，共五个 |

权威决策清单见 [`docs/planning/decision-log.md`](./docs/planning/decision-log.md)。

## 五、当前实现状态

已经完成：

- 产品、架构、上下文、数据和实施规划文档；
- 17 个重要工作面的界面清单；
- UI-PROP-0001 至 UI-PROP-0011 的示意图和提案文档；
- 大盘、策略个股、行业研究个股和 ETF 的统一蜡烛图交互契约；
- 行业资金相对轮动、生命周期结构地图和行业内研究排序设计；
- 文档本地链接和 SVG/PNG 渲染校验。
- WP-0001：Python 3.12/uv、Node 24/pnpm、FastAPI、React/Vite、DuckDB Python API 与 SQLite/WAL 开发底座；
- 五个上下文目录、10 个公共契约及生成的 JSON Schema；
- `make bootstrap`、`make doctor`、`make dev`、`make check`、`make e2e-smoke`；
- 合成 Golden Fixture、架构/文档/密钥/规模检查和开发诊断页。
- REQ-2026-0004 与 ADR-0004：MiniQMT 行情/交易双端口和分阶段接入路线。
- WP-0002A：Tushare/MiniQMT 只读能力矩阵、追加式原始证据、内容寻址数据集、
  SQLite/WAL 台账、DuckDB 精确版本查询和确定性快照构建器。
- WP-0002B：四类严格标准化观察、真实版本化 Parquet 和首个生产 `DataSnapshot`。
- WP-0002B-H1：复用旧正式 Silver，形成 2000 年以来日线和复权因子年度分区。
- WP-0002B-H2：复用旧正式 Silver，形成每日指标、涨跌停和停复牌事件年度分区。
- WP-0002B-H3：形成历史名称/ST 区间和 2000 年以来逐日可交易状态年度分区。
- WP-0002B-H4：形成分红送转公司行为、前/后复权兼容价和连续研究价格指数。
- WP-0002C：真实 MiniQMT SH/SZ/BJ L1 全推、自动退订和不可变实时微批。
- WP-0003：`/dev/ui-lab` 统一价格检查器、桌面/窄屏截图和无未来数据烟测。
- WP-0004：点时股票池、统一日频回测引擎和生产快照小样本贯通。
- WP-0005：事件/关注代理、动量/突破、反转/量价三类候选及 2/5/10 周期。
- WP-0006：5 万元最多两只的战术目标、Shadow 成交与 SQLite/WAL 事件账本。

尚未完成：

- 配股及其他公司行为、BSE 独立交易日历；
- 生产 API 查询、Worker 和数据作业恢复流程；
- 全市场开发期/封存期正式策略证据与晋级结论；
- 持续 Shadow 的日度调度、跨日恢复和正式对账报告；
- MiniQMT 长时守护、断线重连验收，以及账户/交易适配器；
- 任何产品业务页面；当前 React 只实现开发诊断和获批准的 UI Lab。

不要把示意图、需求批准或规划状态描述成已经实现、已经回测、Paper 就绪或 Live 就绪。

## 六、需求与 UI 批准状态

### 已批准需求

| 需求 | 版本 | 含义 |
| --- | --- | --- |
| REQ-2026-0001 | 1.0.1 | 初始产品与规划基线；MiniQMT 现状由 REQ-2026-0004 接管 |
| REQ-2026-0002 | 1.0.1 | 行业资金相对轮动图 |
| REQ-2026-0003 | 1.1.2 | 完整界面、蜡烛图、行业结构与交互补充 |
| REQ-2026-0004 | 1.0.1 | 东莞证券 MiniQMT 能力接入路线 |

### 已批准 UI

| UI 提案 | 版本 | 可作为实现基线的内容 |
| --- | --- | --- |
| UI-PROP-0001 | 0.3 | 应用壳层、大盘指数蜡烛图、行业热力 |
| UI-PROP-0002 | 0.1 | 行业资金相对轮动与动效分镜 |
| UI-PROP-0004 | 0.2 | 短线竞技、策略选股蜡烛图和晋级证据 |
| UI-PROP-0009 | 0.2 | ETF 轮动、ETF 蜡烛图和目标草案 |
| UI-PROP-0011 | 0.1 | 行业生命周期结构地图、行业内研究排序和联动个股蜡烛图 |

### 尚未批准、不得实施对应页面

- UI-PROP-0003 v0.1：今日工作台与异常抽屉；
- UI-PROP-0005 v0.1：因子、行业模型和优化器；
- UI-PROP-0006 v0.1：组合、目标与风险；
- UI-PROP-0007 v0.1：订单、Shadow、异常和对账；
- UI-PROP-0008 v0.1：数据作业、连接、常设授权和恢复。

未批准页面不能因为相邻页面已批准而被顺带实现。非 UI 的本地开发底座、公共契约和数据能力可以使用独立工作包继续。

## 七、统一蜡烛图不可遗漏的交互

大盘指数、策略选出的股票、行业研究股票和 ETF 共用一个价格检查器：

- 日线、周线和月线；
- 蜡烛主窗格与独立成交量窗格；
- MA5、MA20 等少量可关闭均线；
- 底部双端时间范围轴；
- 左右手柄分别调整起点和终点；
- 拖动已选区间整体平移；
- 蜡烛、成交量、均线和策略标记同步缩放；
- 鼠标悬浮显示跨窗格十字线；
- 浮层显示交易日期、开高低收、涨跌额/幅、成交量、成交额和启用均线；
- 空白或数据缺口不插值、不沿用相邻 K 线；
- 封存回放不能显示或预载证据截止时间之后的 K 线。

设计仓已锁定 `lightweight-charts 5.2.0`，统一价格检查器使用 v5 `addSeries` API。

## 八、数据主线与复用边界

首期只建设个股与后续 ETF 共用的最小数据主干：

- 证券主表与名称历史；
- 交易日历；
- 日度不复权 OHLCV 与成交额；
- 复权因子和独立派生复权价格；
- ST、停牌、涨跌停、上市和退市状态；
- 市值、换手和必要估值；
- 龙虎榜 `top_list`，权限允许时增加 `top_inst`；
- 股东户数，并按公告可用时间处理；
- 历史行业归属、行业指数和成分；
- 因子明确使用的小型财务字段集；
- ETF 主表、日行情、规模、流动性和版本化行业映射。

所有研究使用不可变 `DataSnapshot`，遵守点时正确的 `available_at`。不能使用当前行业、当前财务或未来价格重写历史。

可复用来源：

- `/home/ly/work/financial-analysis`：路径已确认存在；仅复用经核验的数据适配思想、财务字段和策略参考；
- `/mnt/e/work/AstraMind_OS`：旧项目路径已确认存在；只迁移必要数据资产、公式、注册表、Fixture 和验证思想；
- Tushare：用户允许后续补齐 2000 年以来可获得的数据，但每个数据集必须记录真实起始日期和权限缺口。

禁止从旧项目整体迁移：

- 发布门禁；
- Formal/Preview 状态机；
- 固定观察期；
- 多用户身份权限；
- 手工 JobRun 和机构式审批；
- 第二套数据真相、策略注册表、执行引擎或任务系统。

## 九、架构与 Vibe Coding 约束

采用本地优先模块化单体，保持五个上下文：

```text
Data
  → Market Regime
  → Strategy Research
  → Portfolio & Risk
  → Trading Execution
```

依赖方向：

```text
domain/contracts
  → application services
  → ports
  → adapters
  → composition root
```

薄腰契约包括：

- `DataSnapshot`
- `FeatureSnapshot`
- `StrategyVersion`
- `PredictionBatch`
- `OptimizationProblem` / `OptimizationResult`
- `PortfolioTarget`
- `StandingMandate`
- `OrderPlan`
- `ExecutionEvent`

代码限制：

- Python/TypeScript 模块目标不超过 250 行；
- React 组件目标不超过 180 行；
- 函数目标不超过 60 行；
- 按业务责任和变化频率拆分，不建立 `utils.py`、`helpers.ts` 或巨型路由；
- 一个工作包尽量拥有一个 feature 目录；
- 高冲突的公共契约、组合根、迁移和设计令牌一次只由一个工作包修改；
- 不进行与当前工作包无关的格式化、依赖升级或清理。

## 十、本机已知环境线索

- 源码仓库位于 WSL 原生文件系统：`/home/ly/work/AstraMind_OS_mini`；
- 旧 AstraMind 位于：`/mnt/e/work/AstraMind_OS`；
- `financial-analysis` 位于：`/home/ly/work/financial-analysis`；
- 用户提供的 ROCm WSL 路径已确认目录存在：`/mnt/e/WSL/Ubuntu-24.04-ROCm`；
- 尚未验证该 ROCm 目录中的 Python、PyTorch、GPU、驱动和当前 WSL 发行版可用性；
- 东莞证券 MiniQMT 已由用户验证：实盘/模拟盘账户读取、本地行情 RPC L1 全推；
- 本机 API 已暴露 `query_stock_asset/positions/orders/trades`、`order_stock`、
  `cancel_order_stock`、`subscribe_quote`、`get_full_tick`、`get_l2_quote` 等接口；
- L2、信用及其他扩展能力仍取决于券商权限和逐项数据质量验证；
- WSL 运行期间禁止执行 `wsl.exe --shutdown` 或终止当前 Codex 发行版。

任何 Token、账户、券商凭证和真实订单数据都不得写入仓库、Fixture、日志或截图。

## 十一、已完成的工作包

`WP-0001：本地开发底座与契约骨架` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0001-local-development-foundation.md`](./docs/planning/work-packages/WP-0001-local-development-foundation.md)。

- Mini 默认端口为 API 8010、Web 5174；旧 AstraMind 正在占用的 8000/5173 未被停止。
- `make doctor` 必需项全部通过；DuckDB/SQLite CLI 和 ROCm/PyTorch 缺失只警告。
- `make check` 耗时 14.74 秒，Python 9 项、Web 1 项测试及全部静态检查通过。
- `make e2e-smoke` 的 Playwright Chromium 流程 1/1 通过，退出后端口已释放。
- 阶段 1C/1D、策略、Shadow 与 MiniQMT 持续行情/交易均未开始。

`WP-0002A：双提供方能力探测与不可变快照框架` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002A-provider-probes-snapshot-framework.md`](./docs/planning/work-packages/WP-0002A-provider-probes-snapshot-framework.md)。

- Tushare `trade_cal`、`stock_basic`、`daily`、`adj_factor`、`daily_basic` 小样本可用；
- MiniQMT `get_full_tick`、交易日历和合约资料可用；
- 闭市有界订阅返回 `empty` 并完成退订；L2 保持 `not_probed`；
- 小窗口 K 线因隔离 Windows Python 缺少 `numpy` 而明确失败，不伪造成功；
- 真实证据仅位于 Git 忽略的 `var/`，没有生产 `DataSnapshot`；
- 未读取账户或导入交易接口。

`WP-0002B：首个生产数据快照` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002B-first-production-data-snapshot.md`](./docs/planning/work-packages/WP-0002B-first-production-data-snapshot.md)。

- 当前快照身份为
  `snapshot:sha256:430fbab6c3fa92ea71f90a4a7e81c05522d5828f3cfc805e09a27b97a17a2780`；
- 数据日期为 2026-07-24，包含证券主表 5,871 行、双交易所日历 25,812 行、
  日线 5,526 行和复权因子 5,544 行；
- 所有日线均能关联证券主表和复权因子，18 条因子无当日 Bar 已显式记录；
- 历史日线与复权因子已完成；完整可交易性仍未完成。

`WP-0002B-H1：复用旧 Silver 的历史日线与复权因子` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002B-H1-legacy-market-history.md`](./docs/planning/work-packages/WP-0002B-H1-legacy-market-history.md)。

- 当前快照为
  `snapshot:sha256:e4971c03b9da6c4a94787136071b72c165f0713cfc983b33ca7630a1fdb023dc`；
- 6,435 个交易日完整覆盖，日线 17,119,507 行、复权因子 17,696,624 行；
- 旧 Silver 只缺 2026-07-15，本次只执行了两个 Tushare 请求；
- 日线缺复权因子为 0，所有历史可用时间均为交易日 18:00；
- 旧 MinIO 原始响应没有复制，保留 `legacy_raw_payloads_external` 缺口。

`WP-0002B-H2：复用旧 Silver 的每日指标与交易约束` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002B-H2-legacy-trading-constraints.md`](./docs/planning/work-packages/WP-0002B-H2-legacy-trading-constraints.md)。

- 当前快照为
  `snapshot:sha256:c897081a39ab131286af148632c029a9b24e9aff3c23e94cdeafff8ad99d09c4`；
- `daily_basic` 17,104,422 行，覆盖 2000-01-04 至 2026-07-24；
- `price_limit` 15,623,040 行，从 2007-01-04 开始，其中 302 行明确不可用；
- `suspension_event` 591,844 行，5 个早期空日已有原始响应证据；
- 8 个逻辑缺口之外没有重复拉取历史，完成后幂等重跑 0.66 秒；
- 日线与每日指标/涨跌停的双向覆盖差异均进入快照 `known_gaps`，没有伪造补值。

`WP-0002B-H3：历史名称/ST 与逐日可交易状态投影` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002B-H3-historical-status-projection.md`](./docs/planning/work-packages/WP-0002B-H3-historical-status-projection.md)。

- 当前快照为
  `snapshot:sha256:14e41516ba38e7a80241c2e837ba13788d88e348599df27e90de2e2e610a47a2`；
- `security_name_history` 13,738 行，覆盖 5,866 只证券，4 个开放区间按下一名称
  起始日闭合；
- `daily_tradability` 17,707,033 行，27 个年度分区，主键全部唯一；
- 964,864 个上市交易日缺名称区间，保持 `unknown`，没有以当前名称倒灌；
- 512,821 行有证据判为整日停牌；74,696 行无 Bar 且无停牌证据，保持未知；
- 缺失或不可用涨跌停价不会被判为可交易；完成后幂等重跑 0.42 秒。

`WP-0002B-H4：公司行为与统一派生复权价格` 已完成，权威工作包见
[`docs/planning/work-packages/WP-0002B-H4-corporate-actions-adjusted-prices.md`](./docs/planning/work-packages/WP-0002B-H4-corporate-actions-adjusted-prices.md)。

- 当前快照为
  `snapshot:sha256:b0542da9ed6ea9d23f6827612002cbba19d2c99eb76224ebb2cf619e757dec2d`；
- `corporate_action` 169,159 条唯一版本记录，54,700 条已实施且有除权日；
- `adjusted_market` 17,119,507 行，27 个年度分区，主键全部唯一；
- 原始 OHLC 是唯一成交价格；标准前/后复权价只作快照绑定兼容序列；
- 默认研究指数按 `pct_chg` 累计，跨年度及长期停牌后连续性偏差为 0；
- 81,302 次因子变化中 54,060 次有已实施分红送转证据，剩余差异显式保留；
- 完成后幂等重跑 0.70 秒。

后续五个本地基线也已完成，权威工作包分别为：

- [`WP-0002C：MiniQMT L1 全推与不可变实时微批`](./docs/planning/work-packages/WP-0002C-miniqmt-l1-realtime.md)；
- [`WP-0003：统一蜡烛图 UI Lab`](./docs/planning/work-packages/WP-0003-unified-candlestick-ui-lab.md)；
- [`WP-0004：点时正确股票池与统一回测引擎`](./docs/planning/work-packages/WP-0004-point-in-time-universe-backtest.md)；
- [`WP-0005：首批三类短线候选`](./docs/planning/work-packages/WP-0005-first-tactical-families.md)；
- [`WP-0006：短线目标组合与本地 Shadow`](./docs/planning/work-packages/WP-0006-tactical-target-local-shadow.md)。

MiniQMT L1 真实会话使用 `xtquant_250516`，形成 26,768 条规范化观察并确认退订。
生产快照的 10 只股票策略运行只是管线烟测，不是封存期证据。UI Lab 的桌面与窄屏
截图保存在 Git 忽略的 `var/evidence/`。

## 十二、后续推荐顺序

保持小工作包推进：

1. 建立 WP-0004/0005 的全市场分批开发期与 2023–2025 封存回放证据；
2. 补齐 `top_list` 后将事件/关注代理升级为可审计龙虎榜事件策略；
3. 扩展 WP-0006 为持续 Shadow 的跨日调度、正式对账与复盘报告；
4. 为 MiniQMT L1 增加长时守护、断线重连和新鲜度告警验收；
5. 阶段 4 分别申请 MiniQMT 只读账户、模拟盘 Paper 和有限 Live 授权。

个股主线不能被完整 ETF、强化学习、全量财务仓库或旧系统整体迁移阻塞。

## 十三、受保护动作

以下动作仍然没有授权：

- 提交或推送 Git 历史；
- 读取或持久化真实 MiniQMT 账户状态；
- 使用 MiniQMT 模拟盘下单；
- 启用 Paper 或 Live；
- 创建或提交真实订单；
- 读取券商账户、持仓或资金；
- 建立第一份真实常设授权；
- 调整 5 万/10 万资金分仓；
- 修改 8%、10%、12% 回撤边界；
- 将策略晋级等同于交易授权；
- 暴露 WSL 服务到非本机地址。

文档、Fixture、本地测试、回测和本地 Shadow 都不等于券商或真实资金授权。

## 十四、交接时的验证结果

- 本地 Markdown 链接：通过；
- 全部 SVG：XML 解析通过；
- 完整界面总览：1920×1200 PNG 已渲染；
- 四个最新 UI 批准记录和蜡烛图交互条款：通过；
- 应用依赖：`uv.lock` 与 `pnpm-lock.yaml` 已生成；
- `make doctor`：0 个必需项失败，3 个可选警告；
- `make check`：17.82 秒；Python 33 项、Web 1 项及全部质量门通过；
- `make e2e-smoke`：Playwright Chromium 1/1，通过；
- 公共契约 JSON Schema：10 个，无漂移；
- WP-0002A：Tushare 5/5 小样本可用；MiniQMT Tick、日历和合约资料可用，K 线明确
  缺少 `numpy`，闭市订阅为空并退订，L2 未探测；
- WP-0002B：首个生产快照已发布并通过精确版本 DuckDB 查询，发布耗时 7.89 秒；
- WP-0002B-H1：2000 年以来日线/复权因子已发布，首次导入 41.16 秒，幂等重跑
  0.42 秒；
- WP-0002B-H2：每日指标、涨跌停和停复牌事件已发布，首次年度导入 51.60 秒，
  无联网证据重发布 8.71 秒，幂等重跑 0.66 秒；
- WP-0002B-H3：名称/ST 与逐日状态已发布；17,707,033 个逐日主键唯一，
  未知名称、无 Bar 和不可用涨跌停价的失败关闭负例通过，幂等重跑 0.42 秒；
- WP-0002B-H4：169,159 条公司行为和 17,119,507 条派生行情已发布；前/后复权
  公式、研究指数连续性和跨整年停牌恢复负例通过，幂等重跑 0.70 秒；
- Git 远端：`origin` 指向 `dafienoly/AstraMind_OS_mini`；
- Git 历史：尚无首个提交。

## 十五、建议复制到新会话的起始指令

```text
请在 /home/ly/work/AstraMind_OS_mini 开始 AstraMind OS Mini 的开发。

先完整读取 AGENTS.md 和 handoff.md，再按其必读顺序读取权威文档。先报告当前 Git、环境、需求和 UI 批准状态，不要假设已有代码或首个提交。

本次规划并实施 WP-0004：建立点时正确股票池和统一回测底座，只消费一个不可变
DataSnapshot，显式使用原始成交价格、研究价格指数和逐日可交易状态。

不得提交、推送、建立持续 MiniQMT 流、读取真实账户、启用 Paper/Live 或进行任何
真实资金动作，除非我在新会话中另行明确授权。
```
