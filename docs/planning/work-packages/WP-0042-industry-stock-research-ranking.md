# WP-0042：行业内个股研究排序

- 状态：已完成
- 需求：REQ-2026-0008 v1.7.0
- 上游：WP-0040、`lifecycle-structure-v1.0.0`
- 阶段：6D
- UI：UI-PROP-0011 v0.1（已批准）
- 授权：本地只读研究；不形成组合目标、订单或 ETF 交易

## 目标

在用户从行业生命周期结构地图选定一个 SW2021 一级行业后，基于同一不可变
`DataSnapshot` 给出可解释、可重建的成分股研究优先级，并在同页显示所选股票的
日/周/月价格证据。

## 非目标

- 不实现 ETF 轮动、策略晋级、PortfolioTarget、Shadow/Paper/Live 或订单；
- 不连接 MiniQMT，不读取账户；
- 不把估值与股东户数上下文冒充完整财务质量模型；
- 不使用未来行业归属、未来财报或前视标签；
- 不迁移旧系统的买入、卖出或止损文案。

## 方法冻结

评分定义为 `industry-research-priority-v1.0.0`：

- 事件/情绪 25%：1 日收益、5 日收益、换手率、成交额参与和近 20 个交易日
  龙虎榜关注；
- 技术/量价 35%：20 日与 60 日收益、120 日价格位置、20 日波动率安全度；
- 基本面上下文 20%：正 PE(TTM)、正 PB、股息率和股东户数变化；缺失项保持缺失，
  不补零；
- 风险安全度 20%：20 日波动率、下行波动率和 60 日回撤的反向分位；
- 反转/修复分作为独立安全约束，急跌和均线破位可压低综合研究优先级，但不是
  方向预测。

行业内有效样本少于 5 时，分位退回全市场横截面。单股有效权重覆盖低于 60% 时显示
“数据不足”；其余只使用“优先研究”“积极关注”“中性观察”。方法未经独立样本外
验证，只用于安排研究顺序。

## 允许文件

- `src/astramind_mini/market_regime/**`
- `src/astramind_mini/composition.py`
- `apps/web/src/market-dashboard/**`
- `apps/web/src/styles.css`
- `tests/unit/test_industry_research_ranking.py`
- `tests/integration/test_industry_research_ranking_api.py`
- `tests/e2e/foundation.spec.ts`
- 本工作包及其引用的需求、数据合同、计划、决策日志和验收记录

## 受影响合同

- `IndustryResearchRankingSnapshot`
- `IndustryResearchRow`
- `PriceChartSlice`

## 验收

1. API 只能读取请求指定或当前正式 `DataSnapshot`，排序、行业归属和价格证据身份一致；
2. 历史行业成员按证据截止日选择，覆盖不足失败关闭；
3. 每行显示六个分项、覆盖率、标签、截止日和缺口；
4. 选择股票后同页切换日/周/月 K 线，刷新后可恢复；
5. 空、加载、陈旧、阻断、错误状态可见；
6. 领域、合同、API、组件和浏览器流程有聚焦自动化证明，并保存真实截图。

## 保护边界

生命周期和排序是市场研究证据，不得直接导出 `PortfolioTarget`、`OrderPlan` 或
`ExecutionEvent`。任何 ETF 映射、调仓或券商行为需要独立需求和工作包。

## 完成记录

- 正式快照：
  `snapshot:sha256:b9d18ef490c98dc02f1db0d3ac36d62c2b2458a4fb1bec79b0d6419da0f24980`；
- 证据截止：2026-07-28；
- 31 个 SW2021 L1 均可用，5,258 个点时成员中 5,257 个达到 60% 覆盖；
- 标签分布：优先研究 414、积极关注 868、中性观察 3,975、数据不足 1；
- API 冷启动读取被约束到最近两年制品，全市场特征在进程内按快照缓存；股票切换只重取
  同快照价格切片；
- 桌面截图：`var/evidence/wp-0042-industry-research-ranking.png`；
- 窄屏截图：`var/evidence/wp-0042-industry-research-ranking-mobile.png`。

聚焦检查：

```text
uv run pytest -q tests/unit/test_industry_research_ranking.py \
  tests/unit/test_industry_lifecycle.py \
  tests/integration/test_industry_research_ranking_api.py \
  tests/integration/test_industry_lifecycle_api.py
npm run typecheck
npm test -- --run src/market-dashboard/MarketDashboard.test.tsx
pnpm exec playwright test tests/e2e/foundation.spec.ts --grep "industry lifecycle"
uv run python scripts/check_repository.py
```

排序相关测试、类型检查、Mypy、Ruff、浏览器流程和 `git diff --check` 通过。全仓
`check_repository.py` 在本包完成时被并行 WP-0041 的
`scripts/benchmark_market_data_sources.py:_benchmark_requests` 124 行阻断（阈值 120）；
该文件不属于本包，未擅自改动。此前扫描的本地链接、SVG、批准记录和密钥检查通过。
