# 需求索引与唯一追踪表

需求文档固化可观察行为、数据边界和受保护决策；工作包记录有界实施及证据。两套编号
独立分配，不要求 `REQ-2026-NNNN` 与 `WP-NNNN` 数字相同。

## 唯一追踪表

下表同时是需求索引，也是仓库唯一的 `REQ → UI-PROP → WP → 测试证据` 映射。
需要完整跨层关系时以本表为准；各 REQ 和 WP 只维护自身状态与直接引用，不建立第二份
平行矩阵。`make check` 是所有已实施工作包的共同质量门。

| REQ | 版本与状态 | UI-PROP | 对应 WP | 实现状态 | 直接测试证据 |
| --- | --- | --- | --- | --- | --- |
| [REQ-2026-0001：初始产品基线](./REQ-2026-0001-initial-product-baseline.md) | 1.0.1；已批准（规划） | 规划基线本身不适用 | [WP-0001](../planning/work-packages/WP-0001-local-development-foundation.md)、[WP-0002A](../planning/work-packages/WP-0002A-provider-probes-snapshot-framework.md)、[WP-0002B](../planning/work-packages/WP-0002B-first-production-data-snapshot.md)、[H1](../planning/work-packages/WP-0002B-H1-legacy-market-history.md)、[H2](../planning/work-packages/WP-0002B-H2-legacy-trading-constraints.md)、[H3](../planning/work-packages/WP-0002B-H3-historical-status-projection.md)、[H4](../planning/work-packages/WP-0002B-H4-corporate-actions-adjusted-prices.md)、[WP-0004](../planning/work-packages/WP-0004-point-in-time-universe-backtest.md)、[WP-0005](../planning/work-packages/WP-0005-first-tactical-families.md)、[WP-0006](../planning/work-packages/WP-0006-tactical-target-local-shadow.md)、[WP-0007](../planning/work-packages/WP-0007-requirement-baseline-closure.md) | 规划基线已完成并退出开发队列；持续约束仍生效 | [契约](../../tests/unit/test_contracts.py)、[架构](../../tests/unit/test_architecture.py)、[需求与 WP 追踪](../../tests/unit/test_requirement_sequence.py) |
| [REQ-2026-0002：行业资金相对轮动图](./REQ-2026-0002-market-relative-rotation-map.md) | 1.1.0；已批准并实现 | [UI-PROP-0002 v0.1](../ui/proposals/0002-market-relative-rotation-map/proposal.md) 已批准并完成核对 | [WP-0010](../planning/work-packages/WP-0010-formal-industry-rotation.md) | 正式价格相对强弱轮动快照、API 与只读回放页已完成；不是直接资金流或交易信号 | [公式、覆盖与不可变存储](../../tests/unit/test_market_rotation.py)、[API 失败关闭](../../tests/integration/test_rotation_api.py)、[React 状态](../../apps/web/src/market/MarketRotation.test.tsx)、[浏览器回放](../../tests/e2e/foundation.spec.ts) |
| [REQ-2026-0003：完整界面示意图与统一蜡烛图交互](./REQ-2026-0003-complete-interface-schematics.md) | 1.1.2；已批准（交互补充） | UI-PROP-0001 v0.3；UI-PROP-0002 v0.1 仅作为 UI Lab 视觉语言；其余准确版本与批准状态见需求正文 | [WP-0003](../planning/work-packages/WP-0003-unified-candlestick-ui-lab.md) | 统一蜡烛图 UI Lab 已完成；产品业务页面按提案状态实施 | [组件与未来数据隔离](../../apps/web/src/UiLab.test.tsx)、[浏览器流程](../../tests/e2e/foundation.spec.ts) |
| [REQ-2026-0004：东莞证券 MiniQMT 能力接入路线](./REQ-2026-0004-dongguan-miniqmt-capability-roadmap.md) | 1.1.0；已批准（只读账户边界） | 不适用 | [WP-0002A](../planning/work-packages/WP-0002A-provider-probes-snapshot-framework.md)、[WP-0002C](../planning/work-packages/WP-0002C-miniqmt-l1-realtime.md)、[WP-0011](../planning/work-packages/WP-0011-miniqmt-readonly-account-reconciliation.md) | 能力探测、L1 实时微批及真实模拟盘只读账户/对账验收已完成；Paper、Live 和订单未授权 | [提供方探测](../../tests/unit/test_provider_probes.py)、[L1 生命周期与微批](../../tests/unit/test_miniqmt_l1.py)、[账户与对账](../../tests/unit/test_miniqmt_account_reconciliation.py) |
| [REQ-2026-0005：短线研究证据与策略晋级](./REQ-2026-0005-tactical-evidence-promotion.md) | 1.0.0；已批准 | [UI-PROP-0004 v0.2](../ui/proposals/0004-tactical-strategy-arena/proposal.md) 已批准；本次无 UI | [WP-0008](../planning/work-packages/WP-0008-tactical-sealed-evidence-promotion.md)、[WP-0013](../planning/work-packages/WP-0013-promoted-target-first-continuous-shadow-cycle.md)；WP-0004～0006 是上游基线 | 反转/量价 10 日版已按准确证据晋级；首个生产 FeatureSnapshot/PredictionBatch 已生成，弱证据与券商禁用状态不变 | [事件点时与发布](../../tests/unit/test_tactical_event_backfill.py)、[封存证据与晋级](../../tests/unit/test_tactical_evidence.py)、[持续 Shadow 身份链](../../tests/unit/test_continuous_shadow.py) |
| [REQ-2026-0006：订单计划、组合风险与持续 Shadow](./REQ-2026-0006-order-plan-risk-shadow.md) | 1.2.0；已批准 | UI-PROP-0003/0006/0007/0008 v0.1 仍待批准；本轮无 UI | [WP-0011](../planning/work-packages/WP-0011-miniqmt-readonly-account-reconciliation.md)、[WP-0012](../planning/work-packages/WP-0012-reconciliation-disposition-continuous-shadow.md)、[WP-0013](../planning/work-packages/WP-0013-promoted-target-first-continuous-shadow-cycle.md)；WP-0006 是上游基线 | 真实只读对账、差异隔离、回撤、OrderPlan 和跨日核心已完成；首周期已启动并等待 2026-07-29 开盘 | [Shadow 基线](../../tests/unit/test_tactical_shadow.py)、[账户与对账](../../tests/unit/test_miniqmt_account_reconciliation.py)、[差异处置与持续 Shadow](../../tests/unit/test_continuous_shadow.py) |
| [REQ-2026-0007：周度长线研究与核心组合](./REQ-2026-0007-core-weekly-portfolio.md) | 1.0.0；草案 | UI-PROP-0005/0006 v0.1 待批准 | 待分配 | 未批准实施 | 待未来 WP 提供 |
| [REQ-2026-0008：市场状态、行业生命周期与 ETF 研究](./REQ-2026-0008-market-regime-etf-research.md) | 1.1.0；行业数据基础已批准，其余草案 | UI-PROP-0001 v0.3、0009 v0.2、0011 v0.1 已批准；本次无 UI | [WP-0009](../planning/work-packages/WP-0009-industry-data-foundation.md) | SW2021 一级分类、历史成员区间与行业指数日线已实现；生命周期、ETF、市场状态和 UI 未开始 | [行业口径与边界](../../tests/unit/test_industry_foundation.py) |
| [REQ-2026-0009：本地日常运行与恢复](./REQ-2026-0009-local-operations-recovery.md) | 1.0.0；草案 | UI-PROP-0008 v0.1 待批准 | 待分配 | 未批准实施 | 待未来 WP 提供 |

## 维护规则

1. 新 WP 必须在标题元数据中写明一个或少量 `REQ-ID + 准确版本`。
2. 一个 REQ 可以对应多个 WP；一个 WP 也可以落实多个相关 REQ。
3. UI 工作包必须同时引用准确的已批准 UI-PROP 版本。
4. 实施、测试或批准状态变化时，只更新本表、对应 REQ 元数据和 WP 结果，不改变
   两套编号。
5. 状态维护不改变需求语义时不提升需求版本；范围、验收或授权边界变化时必须版本化
   REQ。
6. `已批准`、`已实现`、`Shadow`、`Paper` 和 `Live` 是不同状态，不得互相推导。
7. 草案或需要澄清的 REQ 只用于规划，不授权创建实施工作包或改变受保护边界。
