# WP-0033：个股技术与基本面证据工作台

- 状态：已完成
- 需求：REQ-2026-0002 v1.5.1（v1.4.1 初始实现；v1.5.1 悬浮证据维护修订）
- 阶段：6C
- UI 提案：UI-PROP-0002 v0.4（2026-07-28 已批准）
- Owner branch/worktree：`codex/current-work-checkpoint-20260728` /
`/home/ly/work/AstraMind_OS_mini`

## 目标

在“市场 → 行业 → 相对轮动 → L2 → 个股”中提供一个同快照的只读证据工作台：
四象限或成分列表选择股票后，同步显示日/周/月 K、五条均线、成交量、一个技术指标
副图、悬浮至截止日收益、基本面与股东集中趋势。

## 非目标

- 不增加分钟线、盘中实时价、筹码峰或持仓成本分布；
- 不把技术指标、股东户数或四象限位置解释为买卖信号；
- 不创建策略、组合目标、订单、Paper、Live 或券商动作；
- 不改变正式行业轮动公式、逻辑坐标、象限或事件身份。

## 允许修改

- `src/astramind_mini/market_regime/contracts/hierarchy.py`
- `src/astramind_mini/market_regime/adapters/hierarchy_queries.py`
- `src/astramind_mini/market_regime/adapters/snapshot_hierarchy.py`
- `apps/web/src/market/`
- `apps/web/src/styles.css`
- `tests/unit/test_market_hierarchy_queries.py`
- `tests/integration/test_rotation_api.py`
- `tests/e2e/foundation.spec.ts`
- `scripts/e2e_rotation_fixture.py`
- 本工作包直接关联的需求、数据契约、计划与 UI 提案文档

## 高争用文件

- `src/astramind_mini/composition.py`：只在独立 API 路由确有必要时修改；
- `apps/web/src/styles.css`：只增加 `stock-evidence-*` 命名空间；
- `docs/requirements/README.md` 与分阶段计划：只更新本工作包状态。

## 上下文与契约

- 受影响上下文：Data、Market Regime；
- 修改 `IndustryHierarchyView`，增加选中股票的点时价格与证据切片；
- 兼容性：现有层级字段保持不变，新增字段有安全空值；旧快照仍可返回明确缺口。

## 数据与点时影响

- 数据集：`daily_market`、`daily_basic`、`shareholder_count`、`security_master`；
- 行情与每日指标只读取 `trade_date <= as_of`；股东户数只读取
  `available_at <= as_of` 当日证据截止；
- 一个响应只使用一个 `DataSnapshot`，不跨快照补齐股东户数；
- 不重写历史数据。当前快照没有 `shareholder_count` 时显示可恢复缺口。

## UI 影响

- 用户可从四象限或列表选择股票，选择状态唯一；
- 批准提案：UI-PROP-0002 v0.4；
- 必须覆盖 Loading、Empty、Stale、Blocked、Error、字段缺失和刷新恢复；
- 截图：1440×900 与 390×844。

## 风险与授权

- 风险/mandate：无影响；
- Broker/Live：严格无连接、无写入；
- 用户决定：UI-PROP-0002 v0.4 已明确批准。

## 验收

1. Given 足够历史数据，When 切换日/周/月和均线/副图，Then 所有序列按同一周期同步；
2. Given 悬浮历史 Bar，When 显示图例，Then 展示准确起止日期与截止日累计涨跌幅；
3. Given 四象限或列表选择股票，When 请求完成，Then URL、节点、列表、K 线和证据一致；
4. Given 当前快照缺少基本面或股东户数，Then 显示数据集/字段缺口，不填零、不跨快照；
5. Given 窄屏，Then 四象限、图表、指标和证据按批准顺序可访问且不隐藏截止时间。
6. Given 用户在个股层切换股票，When 新证据仍在读取，Then 四象限和列表保持挂载，
   只在价格与证据区域显示局部加载；失败时保留上一份完整证据并可再次点击重试。
7. Given 用户悬浮历史 Bar，When 十字光标日期变化，Then 基本面和股东集中趋势按
   悬浮日的实际可用时间点时切换；公告前不得显示未来证据，且 hover 不触发请求。

## 检查

```text
uv run pytest tests/unit/test_market_hierarchy_queries.py tests/integration/test_rotation_api.py
pnpm --filter @astramind/web test
pnpm --filter @astramind/web lint
pnpm --filter @astramind/web typecheck
pnpm --filter @astramind/web build
uv run mypy
make docs-check
make e2e-smoke
```

## 交接

- 文件：后端契约与查询位于 `market_regime/contracts/hierarchy.py`、
  `adapters/stock_evidence_queries.py` 和 `adapters/snapshot_hierarchy.py`；前端工作面位于
  `StockHierarchyWorkbench.tsx`、`StockPriceWorkbench.tsx`、`PriceChart.tsx`、
  `StockEvidencePanel.tsx` 和 `stockIndicators.ts`；
- 检查与结果：9 个聚焦 Python 单元/集成测试、21 个前端测试、TypeScript、ESLint
  与 5 个 Playwright 流程通过；局部刷新修订后前端增至 22 个测试，Playwright 通过
  700ms 人工延迟验证工作台不卸载；完整 `make check` 结果见最终交付记录；
- 截图：Git 忽略目录
  `var/evidence/wp-0033-stock-evidence-workbench.png` 和
  `var/evidence/wp-0033-stock-evidence-workbench-mobile.png`；v1.5.1 悬浮联动证据为
  `var/evidence/wp-0033-hover-synchronized-evidence.png`；
- 假设：周/月先裁剪日线再聚合；默认 MA5/10/30 与 MACD；
- 未执行受保护动作：任何券商连接、订单、Paper 或 Live；
- 运行边界：当前生产快照若不含 `shareholder_count`，页面显示
  `shareholder_count_not_in_snapshot`，等待后续日度快照纳入该数据集；不会跨快照补齐。

### v1.5.1 悬浮证据维护修订

- `StockEvidence` 保留截止日字段，并追加同快照 `fundamental_history` 与
  `shareholder_concentration_history`，保持旧消费者兼容；
- 后端返回最近 300 个日度观察及历史周/月末观察，股东序列严格按
  `available_at <= as_of` 裁剪；
- `PriceChart` 通过既有 `subscribeCrosshairMove` 上报 Bar 日期，工作台只在内存中
  选择当时已可用证据，不重建图表、不请求 API；
- 点时选择、公告前失败关闭、API 序列化和 Playwright 日期/收盘同步均有自动化证明。
