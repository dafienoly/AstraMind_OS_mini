# WP-0049：统一应用壳层、顶部导航与分层 Loading

- 状态：`implemented`
- 需求：REQ-2026-0003 v1.7.0
- 阶段：6H
- UI 提案：UI-PROP-0001 v0.7（`approved`）
- 前置：用户准确批准 UI-PROP-0001 v0.7

## 目标

以一个持续挂载的应用壳层统一全系统一级导航、市场二级导航、决策状态带、异常入口和
路由加载反馈；删除页面私有导航副本，使 ETF、行业及其他子页面切换时导航完全一致，
等待期间始终有稳定且真实的 Loading 反馈。

## 非目标

- 不改变五个一级入口的业务语义；
- 不新增一级导航或独立“订单”入口；
- 不重做各业务页面内容、图表、盘口或研究公式；
- 不新增 MiniQMT、账户、委托、撤单、Paper/Live 或交易行为；
- 不以全局状态容器接管各领域业务状态。

## 允许文件

- `apps/web/src/app-shell/`
- `apps/web/src/App.tsx`
- `apps/web/src/market-dashboard/MarketPage.tsx`
- `apps/web/src/market-dashboard/MarketChrome.tsx`
- `apps/web/src/market/RotationPanels.tsx`
- `apps/web/src/market/RotationReadyView.tsx`
- `apps/web/src/operations/OperationsShell.tsx`
- 相关前端测试、样式与本工作包文档

## 高冲突文件

- `apps/web/src/App.tsx`
- `apps/web/src/styles.css`
- `tests/e2e/foundation.spec.ts`

## 上下文与契约

- 领域上下文不变；应用壳层只消费页面声明，不拥有 Data、Market Regime、Strategy、
  Portfolio 或 Trading Execution 业务规则。
- 新增小型前端契约：
  - `PrimaryDestination = today | market | strategy-arena | portfolio | system`
  - `MarketDestination = overview | stocks | industries | etf`
  - `IndustryDestination = heatmap | lifecycle | rotation`
  - `RouteLoadState = idle | navigating | loading_content | connecting_realtime | ready | error`
- 页面只导出目的地声明和内容；导航清单、标签、顺序及 `aria-current` 由壳层唯一拥有。

## 复用与依赖审查

- 复用现有五入口语义、决策状态带、市场页签和状态色，不另建视觉系统。
- 将 `MarketTopbar`、`RotationHeader` 与 `OperationsShell` 的重复一级导航收敛到
  `AppShell`；页面不得反向导入壳层内部实现。
- `MarketSubnav` 是唯一市场二级导航；相对轮动、ETF 和生命周期只声明当前目的地。
- Loading 复用一个无业务含义的 `RouteProgress` 和 `ContentSkeleton` 原语；具体页面
  只提供阶段标签和骨架变体，禁止来源页面布尔开关和万能组件。
- 兼容适配器只允许在本工作包内短暂存在，WP-0049 验收时删除。

## 实施

1. 建立持续挂载的 `AppShell`，集中渲染唯一顶部一级导航、异常入口和路由进度；
2. 统一五入口注册表，移除运营页“订单替代策略竞技场”和市场页禁用占位差异；
3. 建立唯一 `MarketSubnav`，覆盖大盘、个股观察、行业、ETF 和行业三种内部模式；
4. 采用客户端路由切换，保留壳层、决策状态带和可取消的在途请求；
5. 路由开始 100 ms 内显示顶部进度；超过 300 ms 显示阶段说明和目标页稳定骨架；
6. 分离首次页面 Loading、路由 Loading、局部刷新和实时连接，局部失败不清空整页；
7. 为可计数批次显示 `n/N`；不可计数网络请求只显示阶段，不伪造百分比；
8. 支持 `aria-live`、键盘焦点恢复、`prefers-reduced-motion` 和窄屏顶部导航；
9. 删除重复导航 JSX/CSS，加入依赖与代码扫描，防止页面再次声明一级导航。

## 验收

1. 全仓只有一个一级导航注册表和一个渲染实现；
2. 任一路由的一级入口准确为五个，顺序一致，“订单”不在一级导航；
3. 六个市场目的地在 Loading、Error 和 Ready 状态使用同一市场二级导航；
4. 点击导航后 100 ms 内出现可访问的切换状态，慢请求超过 300 ms 显示稳定骨架；
5. 导航、决策状态带、异常入口和返回路径在加载或错误时不消失；
6. 盘口、图表、实时覆盖等局部刷新不触发整页 Loading；
7. 快速连续切换会取消旧请求，旧响应不能覆盖新页面；
8. 浏览器后退/前进恢复准确入口、查询参数和焦点；
9. 1440×900 与 390×844 截图符合 UI-PROP-0001 v0.7；
10. 无 MiniQMT 新调用、账户读取或交易动作。

## 检查

```text
pnpm --dir apps/web test
pnpm --dir apps/web build
uv run pytest tests/unit/test_architecture.py
make docs-check
make e2e-smoke
```

## 受保护边界

界面批准不授权 MiniQMT 账户、Paper/Live、委托或真实资金动作。

## 实现结果

- `AppShell` 唯一拥有五入口和市场/行业子导航；
- 页面内重复导航全部删除，同源链接使用 History API 切换并支持前进/后退；
- 路由开始即显示顶部反馈，300 ms 后显示阶段骨架，页面上报真实阶段；
- Loading/Error 不卸载导航，局部刷新继续由各工作面自行管理；
- 代码扫描只剩一个一级导航渲染点，并有组件测试锁定五入口和慢加载。
- `make e2e-smoke` 已刷新 1440×900 与 390×844 市场截图；对照 v0.7 确认桌面和窄屏
  都只有顶部导航，市场子导航条目及顺序一致。应用内 Browser 本轮不可连接，截图由
  仓库受控 Playwright 流程生成。
