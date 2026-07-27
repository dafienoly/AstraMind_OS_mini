# 文档总览

这是面向用户与 Coding Agent 的权威文档入口。

## 产品与需求

- [产品基线](./product/product-baseline.md)
- [需求索引](./requirements/README.md)
- [REQ-2026-0001：初始产品基线](./requirements/REQ-2026-0001-initial-product-baseline.md)
- [REQ-2026-0002：行业资金相对轮动图](./requirements/REQ-2026-0002-market-relative-rotation-map.md)
- [REQ-2026-0003：完整界面示意图](./requirements/REQ-2026-0003-complete-interface-schematics.md)
- [REQ-2026-0004：东莞证券 MiniQMT 能力接入路线](./requirements/REQ-2026-0004-dongguan-miniqmt-capability-roadmap.md)

## 领域与架构

- [领域上下文图（Agent 内部英文文档）](../CONTEXT-MAP.md)
- [架构基线](./architecture/architecture-baseline.md)
- [ADR-0001：本地优先的模块化单体](./adr/0001-local-first-modular-monolith.md)
- [ADR-0002：券商执行前必须跑通本地 Shadow](./adr/0002-shadow-before-broker-execution.md)
- [ADR-0003：行业生命周期是上游市场状态证据](./adr/0003-industry-lifecycle-upstream-signal.md)
- [ADR-0004：MiniQMT 行情与交易使用独立端口](./adr/0004-miniqmt-split-market-data-and-trading-ports.md)

## 数据

- [数据产品与点时正确契约](./data/data-contracts.md)

## 界面

- [信息架构](./ui/information-architecture.md)
- [完整界面清单](./ui/interface-inventory.md)
- [视觉方向](./ui/visual-direction.md)
- [界面提案与批准流程](./ui/proposal-process.md)
- [UI-PROP-0001：应用框架、大盘与行业看板](./ui/proposals/0001-shell-market-dashboard/proposal.md)
- [UI-PROP-0002：行业资金相对轮动图](./ui/proposals/0002-market-relative-rotation-map/proposal.md)
- [UI-PROP-0003：今日工作台与异常抽屉](./ui/proposals/0003-today-attention/proposal.md)
- [UI-PROP-0004：短线策略竞技场与晋级证据](./ui/proposals/0004-tactical-strategy-arena/proposal.md)
- [UI-PROP-0005：因子研究、行业模型与组合优化器](./ui/proposals/0005-core-research-optimizer/proposal.md)
- [UI-PROP-0006：组合总览、目标桥接与回撤风险](./ui/proposals/0006-portfolio-risk/proposal.md)
- [UI-PROP-0007：公共订单计划、Shadow 执行与对账](./ui/proposals/0007-order-execution/proposal.md)
- [UI-PROP-0008：数据运行、连接状态与常设授权](./ui/proposals/0008-system-operations/proposal.md)
- [UI-PROP-0009：行业 ETF 轮动研究与目标](./ui/proposals/0009-etf-rotation/proposal.md)
- [UI-PROP-0010：完整界面总览](./ui/proposals/0010-full-interface-atlas/proposal.md)
- [UI-PROP-0011：行业生命周期结构地图与行业内研究排序](./ui/proposals/0011-industry-lifecycle-research/proposal.md)

## 规划与开发

- [分阶段实施计划](./planning/phased-implementation-plan.md)
- [决策记录](./planning/decision-log.md)
- [WP-0001：本地开发底座与契约骨架](./planning/work-packages/WP-0001-local-development-foundation.md)
- [WP-0002A：双提供方能力探测与不可变快照框架](./planning/work-packages/WP-0002A-provider-probes-snapshot-framework.md)
- [WP-0002B：首个生产数据快照](./planning/work-packages/WP-0002B-first-production-data-snapshot.md)
- [WP-0002B-H1：复用旧 Silver 的历史日线与复权因子](./planning/work-packages/WP-0002B-H1-legacy-market-history.md)
- [WP-0002B-H2：复用旧 Silver 的每日指标与交易约束](./planning/work-packages/WP-0002B-H2-legacy-trading-constraints.md)
- [WP-0002B-H3：历史名称/ST 与逐日可交易状态投影](./planning/work-packages/WP-0002B-H3-historical-status-projection.md)
- [WP-0002B-H4：公司行为与统一派生复权价格](./planning/work-packages/WP-0002B-H4-corporate-actions-adjusted-prices.md)
- [WP-0002C：MiniQMT L1 全推与不可变实时微批](./planning/work-packages/WP-0002C-miniqmt-l1-realtime.md)
- [WP-0003：统一蜡烛图 UI Lab](./planning/work-packages/WP-0003-unified-candlestick-ui-lab.md)
- [WP-0004：点时正确股票池与统一回测引擎](./planning/work-packages/WP-0004-point-in-time-universe-backtest.md)
- [WP-0005：首批三类短线候选](./planning/work-packages/WP-0005-first-tactical-families.md)
- [WP-0006：短线目标组合与本地 Shadow](./planning/work-packages/WP-0006-tactical-target-local-shadow.md)
- [本地开发指南](./development/local-development.md)
- [Vibe Coding 规范（Agent 内部英文文档）](./development/vibe-coding.md)
- [工作包模板（Agent 内部英文文档）](./development/work-package-template.md)
