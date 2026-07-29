# WP-0034：轮动方向速度分类、筛选与排序

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0002 v1.5.0
- 阶段：6C
- UI 提案：UI-PROP-0002 v0.5（`approved`）
- 日期：2026-07-28
- 券商授权：无；纯只读研究显示

## 目标

把当前含糊的“加速/减速”拆成加速上升、减速上升、加速下跌、减速下跌，并让 L1、
L2 和个股层使用同一套象限、运动状态、坐标和速度筛选排序口径。

## 非目标

- 不把“上升/下跌”解释为股票或行业指数绝对价格涨跌；
- 不改变 `rotation-index-ew-v1.0.0` 逻辑坐标、象限和确认事件；
- 不增加策略、推荐、订单、Paper、Live 或券商动作；
- 不在浏览器重新请求业务数据或写回运动分类。

## 运动口径

运动状态是显示层版本化派生 `rotation-motion-v2.0.0`：

```text
dy_t = relative_momentum_t - relative_momentum_(t-1)
previous_dy = relative_momentum_(t-1) - relative_momentum_(t-2)
speed_t = abs(dy_t)
acceleration_t = abs(dy_t) - abs(previous_dy)
```

- `dy_t > epsilon` 且 `acceleration_t > epsilon`：加速上升；
- `dy_t > epsilon` 且不满足加速：减速上升；
- `dy_t < -epsilon` 且 `acceleration_t > epsilon`：加速下跌；
- `dy_t < -epsilon` 且不满足加速：减速下跌；
- 历史不足或 `abs(dy_t) <= epsilon`：平稳。

`epsilon` 固定进入版本定义，首期建议 `0.01` 个逻辑坐标点。“转强/转弱”继续作为
中性带连续确认事件，不能再与速度状态使用同一个互斥字段。

## 筛选与排序

- 适用范围：L1、父级内/全部 L2、当前 L2 有效成分股；
- 筛选：名称/代码、象限、运动状态、近期确认事件；
- 排序：名称、相对趋势 X、相对动量 Y、最新速度、距中心距离；
- 排序方向：升序/降序；
- 列表行显示排名、名称/代码、X/Y、速度和运动状态；
- 选中对象被筛掉时检查器继续保留，并显示“当前选择不在筛选结果中”；
- 空结果不自动回退到全部对象；
- 筛选和排序进入 URL；hover、动画插值和打开下拉框不进入 URL。

## 允许修改

- `apps/web/src/market/rotationIdentity.ts`
- `apps/web/src/market/rotationTypes.ts`
- `apps/web/src/market/useRotationDerived.ts`
- `apps/web/src/market/RotationToolbar.tsx`
- `apps/web/src/market/IndustryCombobox.tsx`
- `apps/web/src/market/HierarchyPlot.tsx`
- `apps/web/src/market/IndustryHierarchyExplorer.tsx`
- `apps/web/src/market/StockHierarchyWorkbench.tsx`
- `apps/web/src/market/rotationScreening.ts`
- `apps/web/src/market/RotationScreeningControls.tsx`
- `apps/web/src/market/RotationRankedList.tsx`
- `apps/web/src/market/useHierarchyScreening.ts`
- `apps/web/src/styles.css`
- 直接关联的单元、React、Playwright 测试和权威文档

## 验收

1. 四种方向速度状态使用合成轨迹逐一验证，临界值和平稳状态有负向测试；
2. 行业和个股层使用同一分类函数，相同历史得到相同状态；
3. 象限与运动状态组合筛选后，画布淡化集合与列表结果一致；
4. X、Y、速度、距中心和名称排序稳定，完全相同时以代码升序消歧；
5. 筛选排序不触发业务网络请求，播放期间仍使用当前逻辑日；
6. URL 刷新恢复全部筛选排序状态；
7. 桌面和窄屏不遮挡截止日、只读边界和空结果。

## 用户决定

2026-07-28 已收到明确批准：

```text
批准 UI-PROP-0002 v0.5，并实施 WP-0034。
```

## 完成证据

- `rotation-motion-v2.0.0` 使用最近三个完整逻辑日和固定
  `epsilon=0.01` 派生四种方向速度状态及平稳状态；
- L1、L2 与个股复用 `rotationScreening.ts`，支持名称/代码、象限、运动状态、
  近期事件筛选，以及名称、X、Y、速度、距中心的稳定排序；
- 未匹配节点只淡化，列表不回退；当前选择被筛掉时检查器、K 线和证据继续保留；
- L1、L2、个股筛选状态分别写入 URL，筛选排序不触发业务请求；
- 单元与 React：`pnpm --dir apps/web test`，31 项通过；
- 仓库质量门：`make check`，168 项 Python、31 项前端测试及构建全部通过；
- 浏览器：`make e2e-smoke`，5 项通过，并验证本地筛选排序无轮动业务重取；
- 实图：`var/evidence/wp-0034-motion-filter-sort.png`、
  `var/evidence/wp-0034-motion-filter-sort-mobile.png`、
  `var/evidence/wp-0034-motion-filter-sort-stock.png` 和
  `var/evidence/wp-0034-motion-filter-sort-stock-mobile.png`。
