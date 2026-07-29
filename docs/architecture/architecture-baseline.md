# 架构基线

- 状态：规划基线
- 实现状态：本地底座、公共契约、数据持久化与历史行情快照已建立

## 总体形态

AstraMind OS Mini 使用本地优先的模块化单体，在保持研究、组合和执行概念分离的同时，不承担微服务和机构级任务治理的运维成本。

```text
Tushare / 可复用本地数据
            │
            ▼
      数据适配与快照 ◀── MiniQMT 行情端口
            │
            ├──────────────────┐
            ▼                  ▼
        市场状态            策略研究
            │                  │
            └────────┐         ▼
                     └──▶ 组合与风险
                              │
                              ▼
                         OrderPlan 端口
                      ╱      │       ╲
                     ▼       ▼        ▼
             Research Shadow Local Replay  MiniQMT 网关
              （并行研究）   （测试/演练） （Paper / Live）
```

## 已验证技术方向与计划运行组件

| 组件 | 职责 | 初始技术方向 |
| --- | --- | --- |
| 本地 API | 组合根、查询、命令、进度 | FastAPI；WP-0001 已验证健康入口 |
| Web 界面 | 用户工作流和可视解释 | React + TypeScript + Vite；当前仅开发诊断页 |
| 研究存储 | 历史列式数据与分析 | Parquet + DuckDB Python API；WP-0002B-H1/H2 已发布行情、每日指标和交易约束年度分区 |
| 控制台账 | 作业、版本、授权、计划、事件 | Python `sqlite3` / SQLite WAL；当前记录探测、数据集与快照 |
| 模型 Worker | CPU/GPU 训练和批量预测 | Python；验证后使用 PyTorch/ROCm |
| Research Shadow 引擎 | 每个准确候选独立虚拟账本和登记后前向研究证据；不形成券商账户或 Paper 成熟度 | Strategy Research 内的 Python 应用服务；未实施 |
| Local Replay 适配器 | 本地确定性成交、故障测试与恢复演练；不形成前向晋级证据 | Python |
| 本地运行基础设施 | 日度窗口决策、外部备份和隔离恢复演练 | 显式 Python 命令；不使用常驻调度平台 |
| MiniQMT 行情网关 | L1/L2、订阅、历史资料与连接状态 | Data 端口；逐能力核验 |
| MiniQMT 交易网关 | 账户、委托、撤单、回调与对账 | Trading Execution 端口；分级授权 |

WP-0001 已在 Python 3.12、Node 24、`uv` 和 `pnpm` 环境中核验上述方向并锁定
依赖。WP-0002A/2B 已实现 Data 上下文的追加式原始层、内容寻址 Parquet、原子当前
指针、SQLite/WAL 台账和精确版本 DuckDB 查询。领域契约不依赖 FastAPI、DuckDB、
SQLite 或前端库。

## 依赖方向

单个上下文内部：

```text
领域与契约
    ↓
应用服务
    ↓
端口
    ↓
适配器
    ↓
组合根
```

依赖指向内层。领域层不能导入 FastAPI、DuckDB、Tushare、React、MiniQMT 或文件系统路径。

跨上下文只能导入公共契约。市场状态不能直接读取策略仓库；交易执行不能导入模型内部模块。

## 高内聚、低耦合与复用纪律

系统级复用遵循“先统一语义和契约，再复用实现，最后才复用页面组合”的顺序。复用不是把
不同业务塞入一个万能模块，也不是因为字段形状相似就共享同一业务对象。

### 所有权与依赖

- 每条领域规则、状态转换、标准化规则和持久化事实只能有一个明确所有者；其他上下文通过
  其 `public.py`、`api.py`、`index.ts` 或稳定公共契约使用该能力。
- 跨上下文组合发生在应用服务、页面查询模型或组合根，不得从一个上下文导入另一个上下文
  的内部领域、仓储或适配器实现。
- 上下文相关信息使用有名称、可版本化的类型化上下文传递，不使用通用 `dict`、来源页面
  布尔开关或回调把调用方业务规则注入共享组件。
- 提供方、存储、传输和 UI 框架只存在于对应适配器层；领域契约不得泄漏 Tushare API 名、
  MiniQMT SDK 类型、Windows 路径、SSE 客户端或图表库类型。

### 复用层级

新能力应复用满足需求的最低、最稳定层级：

1. 领域公共契约与端口，例如 `DataSnapshot`、规范数据集请求和 `OrderPlan`；
2. 具有明确单位、时间语义和版本的纯计算、格式化与校验规则；
3. 来源路由、原始留存、SSE、新鲜度、连接状态和恢复等基础设施原语；
4. 价格图、范围选择器、状态条、空态和错误态等无业务决策的 UI 基础组件；
5. 由上述能力组合成的单一用途工作台，例如唯一的 `Stock Workbench`。

只有至少两个真实消费者具有相同语义、单位、生命周期和失败状态时，能力才进入共享层。
只有外观相似但语义不同的实现继续留在各自功能内；共享层不得依赖任何具体消费者。

### 禁止的伪复用

- 不建立带大量来源开关、业务分支或可选字段的“万能组件”“万能服务”；
- 不新增承载业务语义的 `utils.py`、`helpers.ts`、巨型 `types.ts` 或共享状态杂物箱；
- 不复制行情订阅、价格格式化、新鲜度判定、图表交互、盘口或错误态后再承诺未来收敛；
- 不允许共享组件因调用页面不同而重新计算策略、行业、组合或风险结论；
- 临时兼容适配器必须有唯一所有者、替换目标和删除工作包，不能成为第二套长期真相。

工作包在新增基础能力前必须列出已检索的现有契约、服务和组件，说明复用、扩展或保持独立的
理由。共享能力必须有小型公共 API、所有消费者的契约测试以及跨上下文依赖检查；当消费者
分支持续增长时，应拆开上层组合并保留底层原语，而不是继续扩大共享组件。

## 计划目录

```text
apps/
  api/
  web/
    src/
      app/
      features/
        today/
        market/
        strategy-arena/
        portfolio/
        system/
      shared/
src/astramind_mini/
  data/
  market_regime/
  strategy_research/
  portfolio_risk/
  trading_execution/
workers/
  model/
gateways/
  miniqmt/
    market_data/
    trading/
contracts/
tests/
  unit/
  contract/
  integration/
  e2e/
docs/
```

每个功能目录拥有自己的界面、查询模型、测试和 UI 提案引用。共享界面目录只放基础组件和设计令牌，不承载业务工作流。

## 核心细腰契约

- `DataSnapshot`
- `FeatureSnapshot`
- `MarketRotationSnapshot`
- `StrategyVersion`
- `PredictionBatch`
- `OptimizationProblem` / `OptimizationResult`
- `PortfolioTarget`
- `StandingMandate`
- `OrderPlan`
- `ExecutionEvent`

这些契约允许数据源、算法、优化器和券商适配器独立演进，同时避免第二套业务真相。

REQ-2026-0007 还登记了未来需要持久化的 `Strategy Lineage`、
`Lineage Evidence Version` 和 `CorePolicyVersion` 身份。它们目前不是已实现公共
契约；后续工作包必须先给出现有 `StrategyVersion`、`PromotionDecision` 和战术专用
服务的兼容迁移方案，不能直接把当前战术字段复用于核心分仓。

REQ-2026-0014 还登记了 `Research Shadow Evidence`、`Paper Sleeve Projection` 和
`Managed Lot` 语义。它们不得被实现成第二套策略注册表、券商账户或执行引擎；准确
公共契约及兼容迁移必须在对应工作包内先行冻结。

## 持久化边界

- 提供方响应作为只追加原始记录保存。
- 标准化历史数据和特征快照是不可变、版本化的 Parquet 产品。
- DuckDB 查询不可变产品，不充当作业或订单权威。
- SQLite/WAL 保存小型事务控制状态和不可变执行事件。
- 大型时序数据不能只为方便而塞入 SQLite。
- “当前快照”只是原子切换指针；一次请求解析后固定具体快照身份。

## Worker 边界

Worker 只执行已经声明的作业，不自行发明“当前状态”。每个作业具有：

- 不可变输入身份；
- 幂等键；
- 租约与心跳；
- 有界重试；
- 可见进度和失败原因；
- 输出清单；
- 在安全情况下可取消。

历史全量重建和模型训练不能隐藏在 API 请求中。

## 本地运行与恢复边界

`local_ops` 是模块化单体的跨上下文运行基础设施，不是第六个业务真相源或执行引擎。
它只消费逻辑文件名、SQLite 一致性快照和内容身份，不导入策略决策或券商协议。

备份目录必须在仓库与 `var/` 外部。恢复演练只写入隔离目录并验证哈希、SQLite 完整性
与事件计数，不覆盖当前投影；真实覆盖式恢复继续需要单独、明确的事故操作决定。

## 模型与优化器边界

模型输出 `PredictionBatch`，不能直接输出券商订单。

核心分仓的 H20/H60 各自拥有 lineage、准确模型产物、校准和证据。组合层只消费两个
明确版本，用固定虚拟预算形成一个 `CorePolicyVersion`；不得让当前模型回填历史，也
不得持久化 H20 × H60 全交叉组合。

优化器统一实现：

```text
solve(OptimizationProblem) -> OptimizationResult
```

核心分仓首期只使用 REQ-2026-0007 的 O0。CVaR、MVSK、YAND、预测级融合和动态周期
权重由独立后置需求管理；任何挑战者都不得改变组合与执行契约。

## 市场状态与相对轮动边界

行业生命周期和 `MarketRotationSnapshot` 都归属市场状态。它们只能消费一个固定的 `DataSnapshot`，并输出描述性市场证据。

动态回放只在浏览器中切换已经加载的有界日期点，不能在每一帧访问提供方、重新计算正式坐标或产生策略/订单。

## 研究与执行边界

Research Shadow 复用 `PortfolioTarget → OrderPlan` 的可执行语义，在 Strategy
Research 中形成独立候选的虚拟账本和研究事实；它不创建券商 `ExecutionEvent`，也不
成为 `ExecutionMode`。Local Replay 使用已记录观察验证相同订单状态和恢复假设。

Paper 与 Live 继续共享 `PortfolioTarget → OrderPlan → ExecutionEvent`。MiniQMT
Paper 只有一个券商 simulation 账户事实，内部短线/核心分仓只负责预算、managed
批次和归因，不能覆盖券商净现金、净持仓、委托或成交。首期同证券同向订单保持独立
意图，相反方向阻断，不做跨策略净额合并。

兼容期内保留已有 `ExecutionMode.SHADOW`、本地账本和检查点的读取能力，禁止重写
历史身份。新的 Research Shadow 使用独立研究身份；活动券商运行只创建 `PAPER` 或
经单独授权的 `LIVE` 计划。MiniQMT 断开时不得用 Research Shadow 或 Local Replay
假设成交替代 Paper 事实。

MiniQMT 适配器位于研究/模型进程之外，不拥有策略逻辑。

## MiniQMT 双端口边界

本机东莞证券 MiniQMT 已由用户验证可读取实盘/模拟盘账户，并可通过本地行情 RPC
接收 L1 全推。一个隔离桥接进程可以复用连接和协议基础，但必须暴露两个逻辑端口：

- Data 端口：订阅/退订、全推、Tick、K 线、交易日历、合约和其他资料；
- Trading Execution 端口：账户、资金、持仓、委托、成交、下单、撤单和回调。

Data 端口的输出进入原始/标准化/快照分层；Trading Execution 端口的输出进入只读
账户快照、启动对账和 `ExecutionEvent`。两端分别记录权限、健康和新鲜度，分别拥有
合同测试与脱敏 Fixture。行情可用不能授权交易，账户可读也不能授权委托。

## 前端边界

前端读取页面专用查询模型，不根据原始字段重新推导策略、组合或风险结论。

每个页面必须显示：

- 真实截止时间和新鲜度；
- 合理层级的数据/模型/公式版本身份；
- Loading、Empty、Stale、Blocked、Error、Disconnected；
- 一个主要动作或明确的只读任务；
- 不要求用户输入内部 ID 的证据入口。
