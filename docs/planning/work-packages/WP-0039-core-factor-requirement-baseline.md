# WP-0039：核心因子需求基线固化

- 状态：已完成
- 需求：REQ-2026-0003 v1.2.1、REQ-2026-0007 v2.0.0、REQ-2026-0011 v1.0.0、
  REQ-2026-0012 v1.0.0、REQ-2026-0013 v1.0.0
- 阶段：阶段 0／规划治理
- UI 提案：UI-PROP-0005 v0.1 已过时；本工作包不创建或批准 v0.2
- 完成日期：2026-07-29

## 目标

把用户已逐项确认的周度核心因子研究、统计证据、组合和 Shadow 边界整理为一个可实施
且不易漂移的权威需求基线，并把 CMM、截面注意力和高级优化器拆成三个独立后置需求。

## 非目标

- 不实现数据、因子、模型、回测、组合、Shadow 或 UI；
- 不修改公共代码契约、数据库、应用配置或运行行为；
- 不批准 UI-PROP-0005 v0.2；
- 不选择 Core Shadow Champion；
- 不连接 MiniQMT，不启用 Paper/Live，不产生订单或真实资金动作。

## 允许文件

- `docs/README.md`
- `docs/requirements/`
- `docs/product/product-baseline.md`
- `docs/contexts/data/CONTEXT.md`
- `docs/contexts/strategy-research/CONTEXT.md`
- `docs/contexts/portfolio-risk/CONTEXT.md`
- `docs/architecture/architecture-baseline.md`
- `docs/adr/0006-separate-horizon-lineages-from-core-policy.md`
- `docs/data/data-contracts.md`
- `docs/planning/phased-implementation-plan.md`
- `docs/planning/decision-log.md`
- `docs/planning/work-packages/WP-0039-core-factor-requirement-baseline.md`
- `docs/ui/information-architecture.md`
- `docs/ui/interface-inventory.md`
- `docs/ui/proposals/0005-core-research-optimizer/proposal.md`

## 受影响契约与保护边界

本工作包只登记未来需要的 `Strategy Lineage`、`Lineage Evidence Version` 和
`CorePolicyVersion` 语义，不修改现有 Python 契约。未来实施发现
`StrategyVersion`、`PromotionDecision` 或战术专用服务不足时，必须另开准确实施工作包
并做兼容迁移，不能在本工作包中顺手扩展。

REQ-2026-0006 的 8%/10%/12% 风险动作继续有效；REQ-2026-0010、Paper/MiniQMT 的
现有工作和用户未提交改动不属于本工作包。

## 验收

1. REQ-2026-0007 v2.0.0 只保留首期核心基线，并冻结因子、标签、费用、统计、O0、
   状态机、晋级和测试口径。
2. CMM、截面注意力和高级优化器各有唯一后置 REQ，不再与核心基线混写。
3. 需求索引中每个 REQ 恰好一行，WP-0039 可追踪到四个准确需求版本。
4. 产品、架构、术语、数据、阶段计划、决策和 UI 状态不互相矛盾。
5. 没有业务代码、券商连接、UI 实现、Shadow/Paper/Live 状态或授权变化。

## 检查

```text
uv run pytest tests/unit/test_requirement_sequence.py
make docs-check
git diff --check
```

## 结果

- 核心需求从开放式访谈转为批准的 v2.0.0 实施规格；
- 三个高复杂度方向被拆出并保持草案；
- 公式、统计、失败关闭和测试细节已进入权威需求；
- UI-PROP-0005 v0.1 被标记为过时，v0.2 仍需单独视觉批准；
- 未授权任何功能实施或券商动作。

2026-07-29 校验结果：需求/WP 顺序测试 3 项通过，Markdown 链接、SVG、文档语言、
UI 批准记录、需求编号、密钥检查和 `git diff --check` 通过。完整 `make docs-check`
仍被本工作包允许文件之外的
`market_regime/adapters/dashboard_heat.py:industry_heat` 与
`data/application/daily_pipeline.py` 文件/函数规模门阻断；本工作包未越界重构这些
并行用户改动。
