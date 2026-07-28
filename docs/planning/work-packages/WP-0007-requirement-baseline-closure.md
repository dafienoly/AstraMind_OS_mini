# WP-0007：REQ-0001 规划基线收口与后续需求拆分

- 状态：已完成
- 需求：REQ-2026-0001 v1.0.1
- 阶段：阶段 0／规划治理
- UI 提案：不适用
- 完成日期：2026-07-27

## 目标

确认 REQ-2026-0001 的规划职责已经完成，使其退出开发队列并继续作为产品、架构、
数据、授权和 Vibe Coding 的持续约束；把尚未实现的业务结果拆入独立需求草案。

## 非目标

- 不把产品规划完成描述为全部功能已实现；
- 不修改公共契约、应用代码、数据、策略或 UI；
- 不批准后续需求的功能实施；
- 不读取 MiniQMT 账户，不启用 Paper、Live 或真实订单；
- 不替用户决定 8%、10%、12% 回撤动作或常设授权范围。

## 允许文件

- `docs/README.md`
- `docs/requirements/`
- `docs/planning/phased-implementation-plan.md`
- `docs/planning/decision-log.md`
- `docs/planning/work-packages/WP-0007-requirement-baseline-closure.md`
- `docs/development/local-development.md`
- 当时的临时交接文件（现已[封存](../../archive/handoff-2026-07-28.md)）
- `tests/unit/test_requirement_sequence.py`

## 收口结论

REQ-2026-0001 的权威入口、五上下文、产品顺序、分仓、公共契约、点时数据边界、
Shadow 先于券商、UI 审批门、快速检查和中文文档边界均已有文档或自动化证据。
其原始范围明确排除应用功能、实际 UI 和券商连接，因此这些能力不作为关闭阻塞项。

后续独立需求为：

- REQ-2026-0005：短线研究证据与策略晋级；
- REQ-2026-0006：订单计划、组合风险与持续 Shadow；
- REQ-2026-0007：周度长线研究与核心组合；
- REQ-2026-0008：市场状态、行业生命周期与 ETF 研究；
- REQ-2026-0009：本地日常运行与恢复。

上述需求均未获得功能实施批准；REQ-2026-0006 还需要先澄清回撤动作和常设授权
边界。

## 验收

1. Given 查看 REQ-2026-0001，When 判断其当前职责，Then 明确显示“规划基线已完成、
   已退出开发队列、持续约束生效”。
2. Given 查看需求索引，When 追踪任何现有或后续需求，Then 只有一张
   `REQ → UI-PROP → WP → 测试证据` 权威表。
3. Given 查看后续需求草案，When 尚未取得实施批准，Then 不得把草案描述为已实现
   或已授权。
4. Given 查看 REQ-2026-0006，When 风险动作尚未冻结，Then 状态保持需要澄清。
5. Given 查看券商边界，When WP-0007 完成，Then 账户、Paper、Live 和真实订单授权
   不发生变化。

## 检查

```text
uv run pytest tests/unit/test_requirement_sequence.py
make docs-check
make check
git diff --check
```

## 结果

- REQ-2026-0001 已从开发队列退出，继续作为持续有效的规划基线；
- 五个后续业务结果已登记为独立需求草案；
- REQ 与 WP 继续独立编号；
- 没有实施业务功能、修改 UI 或扩大券商授权。
