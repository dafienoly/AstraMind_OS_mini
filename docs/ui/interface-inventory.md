# 完整界面总清单

- 清单版本：0.2
- 状态：本轮四个修订提案已批准；UI-PROP-0003、0005、0006、0007、0008 仍待批准
- 对应需求：[REQ-2026-0003](../requirements/REQ-2026-0003-complete-interface-schematics.md)
- 界面实现：未开始

## 总览图

![AstraMind OS Mini 完整界面总览](./proposals/0010-full-interface-atlas/interface-atlas-v0.2.png)

[打开总览 SVG](./proposals/0010-full-interface-atlas/interface-atlas-v0.2.svg)。

总览图用于快速检查信息架构；具体布局和批准以各 UI-PROP 高清图为准。

## 一级入口与工作面

| 工作面 | 建议位置 | 唯一任务 | UI 提案 | 状态 |
| --- | --- | --- | --- | --- |
| 今日工作台 | `/`、`/today` | 今天发生了什么、计划什么、为何行动或不行动 | UI-PROP-0003 | 待批准 |
| 需要你处理 | 全局抽屉 | 只处理超授权、失败和异常 | UI-PROP-0003/0007 | 待批准 |
| 大盘 | `/market?tab=overview` | 用所选宽基指数价格结构与市场广度判断环境 | UI-PROP-0001 v0.3 | 已批准 |
| 行业热力 | `/market?tab=industries&view=heatmap` | 比较行业参与与生命周期 | UI-PROP-0001 v0.2 | 已批准 |
| 相对轮动 | `/market?tab=industries&view=rotation` | 观察行业相对位置和迁移轨迹 | UI-PROP-0002 v0.1 | 已批准 |
| 生命周期结构与行业研究 | `/market?tab=industries&view=lifecycle` | 解释行业结构位置，并在选定行业内确定研究优先级 | UI-PROP-0011 v0.1 | 已批准 |
| ETF 轮动 | `/market?tab=etf` | 解释 ETF 候选、价格核验、拒绝和目标变化 | UI-PROP-0009 v0.2 | 已批准 |
| 短线竞技场 | `/strategies?view=tactical` | 公平比较多类短线逻辑 | UI-PROP-0004 v0.2 | 已批准 |
| 策略证据 | `/strategies?view=evidence` | 检查候选个股价格、逐笔、失败场景和晋级差异 | UI-PROP-0004 v0.2 | 已批准 |
| 因子研究 | `/strategies?view=core-factors` | 评价因子覆盖、衰减、稳定性和相关性 | UI-PROP-0005 | 待批准 |
| 模型/优化器 | `/strategies?view=core-models` | 比较行业模型与组合优化方案 | UI-PROP-0005 | 待批准 |
| 组合总览 | `/portfolio` | 理解当前资金、收益和目标差异 | UI-PROP-0006 | 待批准 |
| 风险与回撤 | `/portfolio?view=risk` | 解释集中、流动性、回撤和处理动作 | UI-PROP-0006 | 待批准 |
| 订单计划 | `/orders?view=plan` | 把目标转换为可理解的订单计划 | UI-PROP-0007 | 待批准 |
| 执行与对账 | `/orders?view=execution` | 解释提交、成交、拒绝和差异 | UI-PROP-0007 | 待批准 |
| 数据与作业 | `/system?tab=data` | 操作数据更新、覆盖和失败恢复 | UI-PROP-0008 | 待批准 |
| 执行设置 | `/system?tab=execution` | 查看 Shadow/MiniQMT、授权和本地恢复 | UI-PROP-0008 | 待批准 |

路由是信息架构建议，不是已实现 API，也不要求每个详情拥有独立 URL。

## 提案目录

| 提案 | 覆盖内容 | 图片 |
| --- | --- | --- |
| [UI-PROP-0001](./proposals/0001-shell-market-dashboard/proposal.md) | 应用框架、大盘指数蜡烛图、行业热力 | [v0.3 已批准](./proposals/0001-shell-market-dashboard/schematic-v0.3.png) · [v0.2 历史批准](./proposals/0001-shell-market-dashboard/schematic-v0.2.png) |
| [UI-PROP-0002](./proposals/0002-market-relative-rotation-map/proposal.md) | 行业资金相对轮动 | [v0.1](./proposals/0002-market-relative-rotation-map/schematic-v0.1.png) |
| [UI-PROP-0003](./proposals/0003-today-attention/proposal.md) | 今日、异常抽屉 | [v0.1](./proposals/0003-today-attention/schematic-v0.1.png) |
| [UI-PROP-0004](./proposals/0004-tactical-strategy-arena/proposal.md) | 短线竞技场、策略选股蜡烛图、证据与晋级 | [v0.2 已批准](./proposals/0004-tactical-strategy-arena/schematic-v0.2.png) · [v0.1](./proposals/0004-tactical-strategy-arena/schematic-v0.1.png) |
| [UI-PROP-0005](./proposals/0005-core-research-optimizer/proposal.md) | 因子、行业模型、优化器 | [v0.1](./proposals/0005-core-research-optimizer/schematic-v0.1.png) |
| [UI-PROP-0006](./proposals/0006-portfolio-risk/proposal.md) | 组合、目标、风险与回撤 | [v0.1](./proposals/0006-portfolio-risk/schematic-v0.1.png) |
| [UI-PROP-0007](./proposals/0007-order-execution/proposal.md) | 订单计划、异常、执行与对账 | [v0.1](./proposals/0007-order-execution/schematic-v0.1.png) |
| [UI-PROP-0008](./proposals/0008-system-operations/proposal.md) | 数据作业、连接、授权和恢复 | [v0.1](./proposals/0008-system-operations/schematic-v0.1.png) |
| [UI-PROP-0009](./proposals/0009-etf-rotation/proposal.md) | ETF 轮动、候选 ETF 蜡烛图与目标 | [v0.2 已批准](./proposals/0009-etf-rotation/schematic-v0.2.png) · [v0.1](./proposals/0009-etf-rotation/schematic-v0.1.png) |
| [UI-PROP-0010](./proposals/0010-full-interface-atlas/proposal.md) | 完整界面总览，仅作索引，不单独授权实现 | [v0.2](./proposals/0010-full-interface-atlas/interface-atlas-v0.2.png) |
| [UI-PROP-0011](./proposals/0011-industry-lifecycle-research/proposal.md) | 行业生命周期结构地图、行业内研究排序与联动个股蜡烛图 | [结构地图 v0.1 已批准](./proposals/0011-industry-lifecycle-research/structure-map-v0.1.png) · [研究排序 v0.1 已批准](./proposals/0011-industry-lifecycle-research/industry-ranking-v0.1.png) |

## 三条核心用户路径

### 每日个股路径

`今日 → 策略证据 → 目标组合 → 订单计划 → Shadow/券商执行 → 对账`

### 长线周度路径

`因子研究 → 行业模型/优化器 → 长线目标 → 风险 → 周度订单计划`

### 市场与 ETF 路径

`大盘指数蜡烛 → 行业热力/生命周期结构/相对轮动 → 行业内研究或 ETF 候选 → 个股/ETF 价格核验 → 策略证据 → 目标组合`

市场观察不能绕过策略证据直接进入订单。

## 全局组件

- 五入口导航；
- 决策状态带；
- “需要你处理”异常入口；
- 页面级截止时间与新鲜度；
- 右侧检查器；
- 指数、个股和 ETF 共用的日/周/月蜡烛图检查器；
- 蜡烛图底部双端范围轴与悬浮逐 K 数据；
- 数据与方法详情；
- 状态：Loading、Empty、Stale、Blocked、Error、Disconnected；
- 刷新恢复；
- 窄屏底栏与底部检查器。

## 不单独建立页面

- 登录、组织、角色或审批中心；
- 发布、Formal/Preview 或能力资格后台；
- 数据集、快照、模型、作业、订单事件各自的 CRUD 管理页；
- 单独的行业生命周期一级入口；
- 单独的“AI 中心”；
- 重复的 Shadow 与 Live 两套工作台。
