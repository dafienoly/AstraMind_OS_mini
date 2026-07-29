# WP-0024：行业相对轮动体验修订

- 版本：1.0.0
- 状态：已实施
- 需求：REQ-2026-0002 v1.2.0
- 阶段：6C
- UI 提案：`UI-PROP-0002 v0.2`，已于 2026-07-28 批准
- 日期：2026-07-28
- 券商授权：不适用；全程只读

## 目标

在不改变 `rotation-index-ew-v1.0.0` 逻辑坐标和快照身份的前提下，让 31 个
`SW2021:L1` 行业的回放连续、可控、不会被画布裁切，并让用户能发现全部行业、选择
轨迹密度和核验完整公式。

## 范围

- 使用一个 `requestAnimationFrame` 循环，在相邻交易日的可视坐标间做有界插值；
- 逻辑日期、象限、详情、统计和事件仅在插值抵达下一交易日后整体切换；
- 建立带内边距的安全绘图区，节点、标签和 SVG 轨迹共享同一坐标映射；
- 边缘标签自动向内翻转，公式截断点显示明确的越界标记；
- 增加“轨迹：选中行业 / 筛选结果 / 全部行业”，默认仍为“选中行业”；
- 全部轨迹使用低透明度，选中行业保持主视觉，标签只服务当前选择；
- 将文本搜索升级为可搜索行业组合框，点击时可浏览全部 31 个一级行业；
- 增加明确的“公式与口径”抽屉，展示收益、等权基准、累计相对状态、EMA、动量、
  稳健 z-score、坐标缩放、截断和事件确认规则；
- 在状态带显示最近完成交易日、快照截止日及 `current / stale / blocked`。

## 非目标

- 不修改轮动公式、行业指数数据或 `MarketRotationSnapshot` 逻辑身份；
- 不加入申万二级行业；“半导体”下钻由 WP-0026 独立承接；
- 不把视觉插值值写入 URL、API、快照、详情或研究证据；
- 不增加策略、目标、订单、Paper、Live 或券商控件；
- 不以平滑动画暗示盘中实时更新或未来预测。

## 允许修改

- `apps/web/src/market/`
- `apps/web/src/styles.css` 中轮动页面的局部样式
- `apps/web/src/market/*.test.tsx`
- `tests/e2e/foundation.spec.ts` 中轮动工作流
- `docs/ui/proposals/0002-market-relative-rotation-map/`
- 本工作包及直接追踪文档

## 高争用文件

- `apps/web/src/styles.css`
- `tests/e2e/foundation.spec.ts`
- `docs/requirements/README.md`
- `docs/planning/phased-implementation-plan.md`

实施前必须确认没有其他工作包正在修改同一轮动组件或共享样式。

## 上下文与契约

- 影响上下文：Market Regime 的只读展示适配层；
- 公共契约：不修改；
- 兼容性：继续消费 WP-0010 的 `MarketRotationSnapshot`；
- URL 增加非瞬态 `trail_mode=selected|filtered|all`，插值进度继续不进入 URL。

## 动效与安全绘图区

- 动画进度 `p∈[0,1]` 只计算
  `display = previous + easing(p) × (next - previous)`；
- 所有可见节点使用相同 `p`，不得形成不同日期的混合画面；
- 播放速度只改变交易日间的持续时间，不改变数据；
- 暂停保留当前可视位置；继续播放时从同一进度恢复或确定性吸附到最近逻辑帧；
- 拖动、回到最新、切页和卸载必须取消唯一动画循环；
- `prefers-reduced-motion` 下禁止自动连续插值，保留上一日/下一日和离散回放；
- 画布使用明确内边距，点在公式边界 `85/115` 时标签仍完全可见；
- `overflow=true` 只改变标记说明，不篡改坐标。

## 必备状态

- Loading、Empty、Stale、Blocked、Provider Error、Data Corrupt、Success；
- Reduced Motion；
- 全部轨迹开启但当前筛选为空；
- 行业组合框无匹配结果；
- 公式抽屉在桌面侧栏和窄屏底部面板均可完整阅读。

## 验收

1. Given 两个连续交易日，When 以 1x 播放，Then 节点在两日逻辑坐标间至少产生多个
   可观察中间帧，且没有逐帧业务请求。
2. Given 任一坐标位于 85 或 115，When 在桌面和窄屏渲染，Then 点、标签、焦点环和
   轨迹均不超出可视绘图区。
3. Given 用户选择“全部行业”，When 回放 60 日窗口，Then 31 条轨迹可见、选中行业
   清楚突出、交互保持流畅且没有额外 API 请求。
4. Given 用户打开行业组合框，When 不输入文字，Then 可以浏览并用键盘选择全部 31
   个一级行业。
5. Given 用户打开公式抽屉，When 核对当前快照，Then 页面展示的公式版本和参数与
   `MarketRotationSnapshot.formula` 一致，并说明它不是直接资金流。
6. Given 用户启用 reduced motion，When 点击播放，Then 页面不执行连续插值，核心
   日期导航仍可完成。
7. Given API 快照落后于预期完成交易日，When 页面加载，Then 显示 `stale`、落后日期
   和恢复入口，不把旧快照标为完整最新。

## 检查

```text
pnpm --dir apps/web test
uv run pytest tests/integration/test_rotation_api.py
make e2e-smoke
make docs-check
git diff --check
```

## 用户决定与实施边界

用户已批准本工作包的功能方向和 `UI-PROP-0002 v0.2` 准确视觉基线。该批准只解除
界面提案门禁，不等于要求开始实施，也不授权改变轮动公式、接入二级行业或产生任何
交易动作。

## 交接

- 前置：`UI-PROP-0002 v0.2` 已批准；
- 完成日期：2026-07-28；
- 实施结果：
  - 相邻交易日共用一个 `requestAnimationFrame` 进度，以 ease-in-out 只插值展示
    坐标；逻辑日期、象限和检查器在帧结束后切换，reduced motion 使用离散回放；
  - 节点、标签和多行业轨迹使用同一安全坐标，边缘标签向内翻转并保留越界说明；
  - 已实现选中、筛选结果、全部行业三种轨迹，可搜索组合框和完整公式抽屉；
  - 新鲜度只消费上游显式 `expected_completed_trade_date` 或阻断标记，不在浏览器
    猜测交易日；实际日度生产和恢复状态仍由 WP-0025 提供。
- 自动证据：
  - `make check`：144 项 Python、8 项 Web 测试及格式、lint、类型、构建、架构、
    文档、密钥、规模和 10 个公共 Schema 全部通过，耗时 26.92 秒；
  - `pnpm --filter @astramind/web test`：5 个测试文件、8 项测试通过；
  - Web TypeScript 与 ESLint 通过；
  - `uv run pytest tests/integration/test_rotation_api.py -q`：2 项通过；
  - 浏览器全流程 4 项通过，耗时 8.34 秒；轮动流程证明插值中间帧、逻辑日期不提前、
    31 条轨迹、公式抽屉和全过程只有一次业务请求。
- 视觉证据：
  - `var/evidence/wp-0024-market-rotation.png`；
  - `var/evidence/wp-0024-market-rotation-mobile.png`。
- 下一安全动作：实施 WP-0025，让交易日历、行业日线、DataSnapshot 和轮动快照在
  收盘后增量更新，并产生页面已能消费的显式新鲜度与恢复状态。
