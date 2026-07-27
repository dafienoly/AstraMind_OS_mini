# WP-0001：本地开发底座与契约骨架

- 状态：已完成
- 需求：REQ-2026-0001 v1.0.0
- 阶段：1A、1B
- UI 提案：不适用；仅有非产品开发诊断页
- 所有者：当前无首个提交的本地 `main` 工作区

## 目标

建立可重复、可诊断、默认快速的本地开发循环和公共契约骨架，为首个
`DataSnapshot` 垂直切片提供稳定底座。

## 非目标

- 不实现阶段 1C/1D、业务 UI、Tushare、策略、回测、模型或 Shadow。
- 不连接 MiniQMT，不启用 Paper/Live，不读取账户或创建订单。
- 不提交、不推送，也不删除交接前已存在的未跟踪 `NUL` 文件。

## 允许文件

- 根工具链、锁文件与配置模板；
- `apps/api/`、`apps/web/` 的开发诊断入口；
- `src/astramind_mini/` 的上下文与公共契约骨架；
- `contracts/schema/`、`scripts/`、`tests/`；
- 本工作包影响的 README、架构、计划、决策和交接文档。

## 契约与数据影响

建立 `DataSnapshot`、`FeatureSnapshot`、`StrategyVersion`、`PredictionBatch`、
`OptimizationProblem`、`OptimizationResult`、`PortfolioTarget`、
`StandingMandate`、`OrderPlan` 和 `ExecutionEvent` 的严格身份骨架。

Golden Fixture v1 完全合成，按 `available_at` 验证点时过滤，不引入真实市场、
账户或订单数据，也不建立生产数据存储。

## 验收

1. `make bootstrap && make doctor` 后必需项通过，可选 CLI/GPU 缺失有明确说明。
2. `make check` 在本机 90 秒预算内完成，并阻断非法跨上下文导入和 Schema 漂移。
3. `make e2e-smoke` 显示“产品界面尚未实现”、API 已连接和券商关闭。
4. 配置拒绝非回环监听，秘密不会出现在 API、日志、Fixture 或仓库扫描结果中。

## 受保护边界

本工作包不授权提交、推送、MiniQMT、Paper、Live、常设授权或真实资金动作。

## 验收结果

- `make doctor`：0 个必需项失败；DuckDB/SQLite CLI 与 ROCm/PyTorch 为可选警告。
- `make check`：14.74 秒；Python 9 项、Web 1 项测试及全部静态检查通过。
- `make e2e-smoke`：Playwright Chromium 1/1 通过，服务退出后端口释放。
- 公共契约：10 个 JSON Schema 与 Pydantic 模型一致。
- 未执行提交、推送、MiniQMT、Paper、Live、账户读取或订单动作。
