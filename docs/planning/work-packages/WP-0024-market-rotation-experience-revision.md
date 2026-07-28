# WP-0024：行业相对轮动体验修订

- 版本：1.0.0
- 状态：视觉前置已批准；等待单独实施指令
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
- 实施证据：React 单元测试、浏览器桌面/窄屏截图、动画请求计数和公式一致性测试；
- 下一安全动作：用户单独指令实施 WP-0024。
