# WP-0003：统一蜡烛图 UI Lab

- 状态：已完成
- 完成日期：2026-07-27
- UI 基线：UI-PROP-0001 v0.3、UI-PROP-0002 v0.1（均已批准）

## 目标与非目标

在 `/dev/ui-lab` 用完全合成的小 Fixture 验证统一价格检查器。只实现 UI Lab，不实现
今日、组合、订单或系统运维产品页面。

## 已实现

- `lightweight-charts 5.2.0` v5 API；
- 日/周/月周期，蜡烛主窗格、独立成交量窗格、MA5/MA20；
- 悬浮十字线与开高低收量图例；
- 双端时间范围控件；
- 决策截止日先裁剪、后聚合，未来 Fixture 不传入图表；
- Loading、Empty、Stale、Blocked、Error、Shadow、Broker Disconnected 状态样本；
- 红涨绿跌同时使用文字与图例，不只依赖颜色；
- 桌面和 390px 窄屏布局。

## 验收

前端 3 项测试通过；Playwright 验证周期切换、双端范围、悬浮数据和截止日，截图位于
Git 忽略的 `var/evidence/wp-0003-ui-lab.png` 与
`var/evidence/wp-0003-ui-lab-mobile.png`。应用内验收浏览器当时没有可用实例，项目
自带的隔离 Chromium 烟测 2/2 通过。
