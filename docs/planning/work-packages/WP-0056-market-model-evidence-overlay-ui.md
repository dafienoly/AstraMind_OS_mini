# WP-0056：市场模型方法与证据带

**状态：** 已完成
- 需求：REQ-2026-0002 v1.9.0、REQ-2026-0008 v2.0.0
**阶段：** 6I
**UI 提案：** UI-PROP-0012 v0.1（2026-07-29 已批准）
**工作分支：** `codex/current-work-checkpoint-20260728`

## 目标

在现有行业热力、相对轮动、生命周期结构、行业内研究顺序和 ETF 轮动工作面显示统一
的方法与证据带，准确解释当前方法、预测周期、证据状态、数据截止和 v2 回退原因。

## 非目标

- 不新增导航、页面或模型管理后台；
- 不训练或激活生产 v2，不缩短点时成员和 ETF 前向价差证据门；
- 不创建 `PortfolioTarget`、`OrderPlan`、Paper/Live 或券商动作；
- 不用模拟预测填充当前没有发布的 v2 结果。

## 允许文件

- `apps/web/src/market-dashboard/model-evidence/`
- `apps/web/src/market-dashboard/`
- `apps/web/src/market/RotationReadyView.tsx`
- `apps/web/src/styles.css`
- `tests/e2e/`
- 本工作包及对应需求、计划、决策和 UI 提案文档

## 高争用文件

- `apps/web/src/styles.css`
- `docs/requirements/README.md`
- `docs/planning/phased-implementation-plan.md`
- `docs/planning/decision-log.md`

## 上下文与契约

- 受影响上下文：Market Regime、Strategy Research；
- 复用公共契约：`GET /api/market/model-status`；
- 新增前端只读类型，不修改后端持久化或模型激活契约；
- v1 回退时训练截止显示“不适用”，数据截止来自当前页面正式快照；不推断不存在的
  v2 训练时间。

## 复用与依赖审查

- 复用现有市场页、状态色、快照截止、刷新恢复和模型状态 API；
- 新组件仅负责跨工作面一致解释，不建立第二套状态来源；
- 不新增依赖，不修改应用路由和五入口壳层。

## 数据与点时影响

- 不新增数据集、快照或历史重建；
- 只读取模型激活状态与当前工作面已有正式截止；
- 状态 API 失败时不把未知显示为健康或继续声称模型有效。

## UI 影响

- 用户可见变化：主画布前增加安静的纸质索引带；行业内排序在其工作区增加同口径带；
- 必备状态：Loading、Error、Blocked、Unvalidated、Fallback、Supported；
- 截图：1440×1000 桌面与 390×844 窄屏。

## 风险与授权

- 风险/授权：只读，不改变模型证据硬门；
- Broker/Live：不连接、不授权、不执行；
- 用户决定：UI-PROP-0012 v0.1 已获准确批准。

## 验收

1. 当五类页面加载时，证据带显示该模型家族的准确方法、证据和截止；
2. 当 v2 未训练或证据不足时，页面明确显示 v1 回退及中文原因，未知不使用绿色；
3. 当状态 API 失败时，保留页面主证据并显示局部错误和重试入口；
4. 周期与原始结构控件具备键盘状态，未发布 v2 时不伪造模型结果；
5. 窄屏先显示身份/回退，再允许周期控件横向滚动且不产生页面级溢出。

## 检查

```text
pnpm --filter @astramind/web test
pnpm --filter @astramind/web typecheck
pnpm --filter @astramind/web lint
pnpm --filter @astramind/web build
pnpm exec playwright test <聚焦市场流程>
python scripts/check_repository.py
```

## 交接

- 新增共享模型状态客户端、StrictMode 安全缓存、证据带组件和五类工作面接线；
- 19 个 Vitest 文件、59 项测试通过；TypeScript、ESLint 与生产构建通过；
- Playwright 桌面/窄屏 2 项流程通过；
- 实际截图：
  - `docs/ui/proposals/0012-market-model-evidence-overlay/actual-desktop-1440x1000.png`
  - `docs/ui/proposals/0012-market-model-evidence-overlay/actual-mobile-390x844.png`
- 与提案的内容差异仅为实际生产状态显示 `fallback_v1`，而不是示意数据中的
  `unvalidated_v2`；布局、层级、状态色和响应式顺序一致；
- 应用内浏览器实例在验收时不可用，实际浏览器流程由仓库 Playwright 完成；
- 未执行任何账户、订单、Paper 或 Live 动作。
