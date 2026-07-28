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
                           ╱       ╲
                          ▼         ▼
                    本地 Shadow   MiniQMT 网关
                                （后续单独授权）
```

## 已验证技术方向与计划运行组件

| 组件 | 职责 | 初始技术方向 |
| --- | --- | --- |
| 本地 API | 组合根、查询、命令、进度 | FastAPI；WP-0001 已验证健康入口 |
| Web 界面 | 用户工作流和可视解释 | React + TypeScript + Vite；当前仅开发诊断页 |
| 研究存储 | 历史列式数据与分析 | Parquet + DuckDB Python API；WP-0002B-H1/H2 已发布行情、每日指标和交易约束年度分区 |
| 控制台账 | 作业、版本、授权、计划、事件 | Python `sqlite3` / SQLite WAL；当前记录探测、数据集与快照 |
| 模型 Worker | CPU/GPU 训练和批量预测 | Python；验证后使用 PyTorch/ROCm |
| Shadow 适配器 | 本地确定性成交与对账 | Python |
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

优化器统一实现：

```text
solve(OptimizationProblem) -> OptimizationResult
```

首期使用稳健受约束优化器，后续可以加入层次风险、贝叶斯、可微优化或受限强化学习挑战者，而不改变组合与执行契约。

## 市场状态与相对轮动边界

行业生命周期和 `MarketRotationSnapshot` 都归属市场状态。它们只能消费一个固定的 `DataSnapshot`，并输出描述性市场证据。

动态回放只在浏览器中切换已经加载的有界日期点，不能在每一帧访问提供方、重新计算正式坐标或产生策略/订单。

## 执行边界

`PortfolioTarget → OrderPlan → ExecutionEvent` 在 Shadow、Paper 和 Live 中共享。不同适配器可以有不同成交行为和协议，但策略身份、风险结论、授权判断、订单意图与对账都必须可见。

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
