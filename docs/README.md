# 文档总览

这是面向用户与 Coding Agent 的权威文档入口。

## 产品与需求

- [产品基线](./product/product-baseline.md)
- [需求索引与唯一追踪表](./requirements/README.md)
- [REQ-2026-0001：初始产品基线](./requirements/REQ-2026-0001-initial-product-baseline.md)
- [REQ-2026-0002：行业资金相对轮动图](./requirements/REQ-2026-0002-market-relative-rotation-map.md)
- [REQ-2026-0003：完整界面示意图](./requirements/REQ-2026-0003-complete-interface-schematics.md)
- [REQ-2026-0004：东莞证券 MiniQMT 能力接入路线](./requirements/REQ-2026-0004-dongguan-miniqmt-capability-roadmap.md)
- [REQ-2026-0005：短线研究证据与策略晋级](./requirements/REQ-2026-0005-tactical-evidence-promotion.md)
- [REQ-2026-0006：订单计划、组合风险与持续 Shadow](./requirements/REQ-2026-0006-order-plan-risk-shadow.md)
- [REQ-2026-0007：周度长线研究与核心组合](./requirements/REQ-2026-0007-core-weekly-portfolio.md)
- [REQ-2026-0008：市场状态、行业生命周期与 ETF 研究](./requirements/REQ-2026-0008-market-regime-etf-research.md)
- [REQ-2026-0009：本地日常运行与恢复](./requirements/REQ-2026-0009-local-operations-recovery.md)
- [REQ-2026-0010：MiniQMT 模拟盘执行与恢复](./requirements/REQ-2026-0010-miniqmt-paper-execution-recovery.md)

## 领域与架构

- [领域上下文图（Agent 内部英文文档）](../CONTEXT-MAP.md)
- [架构基线](./architecture/architecture-baseline.md)
- [ADR-0001：本地优先的模块化单体](./adr/0001-local-first-modular-monolith.md)
- [ADR-0002：券商执行前必须跑通本地 Shadow](./adr/0002-shadow-before-broker-execution.md)
- [ADR-0003：行业生命周期是上游市场状态证据](./adr/0003-industry-lifecycle-upstream-signal.md)
- [ADR-0004：MiniQMT 行情与交易使用独立端口](./adr/0004-miniqmt-split-market-data-and-trading-ports.md)
- [ADR-0005：Paper 接管完整模拟盘账户事实](./adr/0005-paper-adopts-complete-simulation-account.md)

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
- [WP-0007：REQ-0001 规划基线收口与后续需求拆分](./planning/work-packages/WP-0007-requirement-baseline-closure.md)
- [WP-0008：短线事件数据、封存证据与手动晋级](./planning/work-packages/WP-0008-tactical-sealed-evidence-promotion.md)
- [WP-0009：REQ-0008 行业数据基础](./planning/work-packages/WP-0009-industry-data-foundation.md)
- [WP-0010：REQ-0002 正式行业资金轮动](./planning/work-packages/WP-0010-formal-industry-rotation.md)
- [WP-0011：MiniQMT 只读账户快照与启动对账](./planning/work-packages/WP-0011-miniqmt-readonly-account-reconciliation.md)
- [WP-0012：账户差异处置与持续 OrderPlan/Shadow](./planning/work-packages/WP-0012-reconciliation-disposition-continuous-shadow.md)
- [WP-0013：晋级策略新鲜目标与首个持续 Shadow 周期](./planning/work-packages/WP-0013-promoted-target-first-continuous-shadow-cycle.md)
- [WP-0014：持续 Shadow 周期闭环](./planning/work-packages/WP-0014-continuous-shadow-cycle-completion.md)
- [WP-0015：本地日常调度、备份与恢复基线](./planning/work-packages/WP-0015-local-operations-backup-recovery.md)
- [WP-0016：Paper 执行状态机、幂等与离线端口合同](./planning/work-packages/WP-0016-paper-offline-state-machine.md)
- [WP-0017：模拟盘模式锁、完整账户基线与只读回调握手](./planning/work-packages/WP-0017-miniqmt-paper-readonly-handshake.md)
- [WP-0018：首份 Paper StandingMandate 与金丝雀委托](./planning/work-packages/WP-0018-paper-canary-order.md)
- [WP-0019：持续 Paper、幂等恢复与盘后收敛](./planning/work-packages/WP-0019-continuous-paper.md)
- [WP-0020：Paper 操作界面与正式验收](./planning/work-packages/WP-0020-paper-operations-ui.md)
- [WP-0021：Paper 金丝雀真实预检、一次性提交与盘后收敛](./planning/work-packages/WP-0021-paper-canary-real-runtime.md)
- [WP-0022：Paper 金丝雀运行编排器](./planning/work-packages/WP-0022-paper-canary-orchestrator.md)
- [WP-0023A：持续 Paper 离线运行守护、备份恢复与故障演练](./planning/work-packages/WP-0023A-offline-paper-guard-recovery-drills.md)
- [WP-0024：行业相对轮动体验修订](./planning/work-packages/WP-0024-market-rotation-experience-revision.md)
- [WP-0025：日度数据增量与派生快照编排](./planning/work-packages/WP-0025-daily-data-derived-snapshot-orchestration.md)
- [WP-0026：申万二级行业“半导体”下钻](./planning/work-packages/WP-0026-semiconductor-l2-drilldown.md)
- [本地开发指南](./development/local-development.md)
- [Vibe Coding 规范（Agent 内部英文文档）](./development/vibe-coding.md)
- [工作包模板（Agent 内部英文文档）](./development/work-package-template.md)

## 归档

- [非权威历史材料](./archive/README.md)
