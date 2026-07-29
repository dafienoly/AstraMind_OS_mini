# WP-0038：大盘看板与行业热力

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0008 v1.4.0
- 阶段：6A、6B
- UI 提案：UI-PROP-0001 v0.3（已批准）
- 日期：2026-07-29
- 券商授权：无

## 目标

从一个不可变 `DataSnapshot` 构建大盘与行业热力只读投影，提供页面专用 API，并按
UI-PROP-0001 v0.3 实现可刷新、可恢复、可浏览器验收的真实市场工作面。

## 非目标

- 不实现行业生命周期坐标、ETF 轮动、策略信号、组合目标或订单；
- 不在页面/API 请求中调用 Tushare 或 MiniQMT；
- 不把行业相对强弱称为资金净流入；
- 不修改相对轮动公式、快照或层级下钻；
- 不连接账户，不启用 Shadow、Paper 或 Live。

## 允许修改

- `src/astramind_mini/market_regime/` 下独立的大盘与行业热力契约、查询和领域计算；
- `src/astramind_mini/data/` 中 `broad_index_daily` 的规范化、发布和日更接入；
- `src/astramind_mini/composition.py` 的只读市场 API；
- `apps/web/src/market-dashboard/` 及市场路由的最小接线；
- 聚焦单元、集成、组件和浏览器测试；
- 本工作包及直接相关权威文档。

## 高争用文件

- `src/astramind_mini/composition.py`；
- `src/astramind_mini/data/application/dataset_schemas.py`；
- `docs/data/data-contracts.md`；
- `docs/planning/phased-implementation-plan.md`；
- `docs/requirements/README.md`。

## 上下文与契约

- 受影响上下文：Data、Market Regime；
- 新增数据集：`broad_index_daily`；
- 新增页面查询契约：`MarketDashboardProjection`；
- 兼容影响：只追加数据集与 GET API，不改变既有 `MarketRotationSnapshot`。

## 数据与点时边界

- 首期宽基注册表固定为上证指数、深证成指、创业板指、科创 50、沪深 300、中证
  1000，身份来自显式版本，不由简称匹配；
- 宽基日线、行业日线、行业成员、个股行情和交易日历必须来自同一个
  `DataSnapshot`；
- 页面投影固定请求开始时解析出的快照身份与 `as_of`，不得混用运行中切换的 current；
- 周/月 K 从同一宽基日线确定性聚合；浏览器不得展示证据截止日之后的数据；
- 缺少宽基、行业或成员覆盖时保留页面结构并失败关闭，不画演示数据。

## UI 影响

- 用户可在“大盘 / 行业 / ETF 轮动”中进入大盘和行业；ETF 继续显示未实施状态；
- 大盘主画布复用统一价格检查器，展示日/周/月 K、成交量、均线和双端范围轴；
- 行业热力展示收益、相对强弱、广度、成交额变化、波动、覆盖及右侧检查器；
- 必备状态：Loading、Empty、Stale、Blocked、Error；
- 截图尺寸：1440×1000 与 390×844。

## 验收

1. Given 一个包含完整宽基、行业与个股数据的不可变快照，When 查询大盘，Then 六个
   宽基指数、价量 K 线、广度、涨跌停结构、成交额和证据身份使用同一截止日。
2. Given 行业成员与个股行情完整，When 查询行业热力，Then 31 个 L1 的收益、相对
   强弱、广度、成交额变化、波动、覆盖和领先个股可解释且可复算。
3. Given 宽基或行业关键覆盖不足，When 打开页面，Then API/界面显式 Blocked 或
   Stale，不显示 fixture、中心点或前值冒充当前证据。
4. Given 用户切换页签、指数、周期、行业和范围，When 观察网络请求，Then 只复用
   已加载投影，不逐帧或逐 K 请求提供方。
5. Given 桌面与窄屏浏览器，When 完成主要流程，Then 截止日、快照、只读声明、
   红绿辅助符号、刷新恢复和检查器保持可用。

## 检查

```text
uv run pytest tests/unit/test_market_dashboard_projection.py \
  tests/integration/test_market_dashboard_api.py
pnpm --dir apps/web test
pnpm --dir apps/web typecheck
make e2e-smoke
git diff --check
```

## 受保护边界

本工作包只授权本地只读市场研究。它不批准生命周期参数、ETF 策略晋级、券商连接、
Paper、Live 或任何订单动作。

## 完成记录

- 正式数据快照：
  `snapshot:sha256:b9d18ef490c98dc02f1db0d3ac36d62c2b2458a4fb1bec79b0d6419da0f24980`；
- 日度原子提交：
  `daily-pipeline-commit:ca726a2f85eff291d8676ea79f0d5fc66a1f4a62b5f72b7757267970da31b230`；
- 宽基基础共 28,862 行，正式投影截止 2026-07-28，包含 6 个宽基和 31 个 L1；
- `MarketDashboardProjection` 冷查询约 0.73 秒，页面请求不访问提供方；
- Ruff、Mypy、5 个聚焦 Python 测试、46 个前端测试和 7 个 Playwright 浏览器流程
  通过；
- 桌面实图：
  `var/evidence/wp-0038-market-overview.png`、
  `var/evidence/wp-0038-industry-heatmap.png`；
- 窄屏实图：
  `var/evidence/wp-0038-market-overview-mobile.png`、
  `var/evidence/wp-0038-industry-heatmap-mobile.png`，未出现页面级水平溢出；
- 截图对照 UI-PROP-0001 v0.3/v0.2 后，将新工作面壳层收口为桌面窄左栏和窄屏固定
  底栏；主画布、右侧/底部检查器、状态带和热力格保持批准的信息层级；
- 应用内嵌浏览器实例当时不可用，因此未用其他浏览器连接器冒充；仓库内 Chromium
  Playwright 可见流程完整通过并生成上述运行时证据。
