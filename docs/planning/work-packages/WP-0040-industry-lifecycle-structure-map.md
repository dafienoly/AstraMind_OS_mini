# WP-0040：行业生命周期结构地图

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0008 v1.5.0
- 阶段：6D
- UI 提案：UI-PROP-0011 v0.1（已批准）
- 日期：2026-07-29
- 券商授权：无

## 目标

从一个不可变 `DataSnapshot` 计算 SW2021 L1 行业的强势参与率 `S`、低位修复参与率
`L`、阶段、置信度和成交额占比，提供只读 API，并按已批准示意图实现结构地图与可读
行业索引。

## 非目标

- 不实现行业内个股研究排序；该能力后续单列工作包，不预占已分配编号；
- 不实现 ETF 池、映射、策略、目标、组合或 Shadow；
- 不复刻旧 AstraMind 的 Formal/Preview、发布门禁、JobRun 或数据库；
- 不在页面/API 请求中访问 Tushare 或 MiniQMT；
- 不连接账户，不启用 Paper、Live 或任何订单动作。

## 允许修改

- `src/astramind_mini/market_regime/` 下独立的生命周期契约、纯计算和快照适配器；
- `src/astramind_mini/composition.py` 的生命周期只读 GET API；
- `apps/web/src/market-dashboard/` 下的结构地图、读取契约及最小市场路由接线；
- `apps/web/src/styles.css` 中该工作面的局部样式；
- 聚焦单元、集成、组件和浏览器测试；
- 本工作包及直接相关权威文档。

## 高争用文件

- `src/astramind_mini/composition.py`；
- `apps/web/src/styles.css`；
- `docs/planning/phased-implementation-plan.md`；
- `docs/requirements/README.md`。

## 方法合同

方法版本为 `lifecycle-structure-v1.0.0`：

- 每只股票至少需要 120 个有效观测，价格自身位置使用 252 日窗口；
- 5/20/60 日收益除以前一期波动率后映射到正态分布累计概率；
- `M_TS = 0.20×u5 + 0.35×u20 + 0.45×u60`；
- `M_XS` 是 `0.40×z20 + 0.60×z60` 的当日截面百分位；
- 均线结构取 `收盘>EMA20`、`EMA20>EMA60`、`EMA20>5日前 EMA20` 的均值；
- `Position = 100×(0.45×252日自身价格百分位 + 0.35×M_TS + 0.20×M_XS)`；
- `Trend = 100×(0.60×M_TS + 0.25×M_XS + 0.15×均线结构)`；
- 强势概率为
  `sigmoid((Trend-60)/7)×sigmoid((Position-50)/10)`，阈值 `0.50`；
- 低位修复概率为
  `sigmoid((40-Trend)/7)×sigmoid((35-Position)/8)`，阈值 `0.55`；
- 行业 `S`、`L` 分别为最近 3 个交易日强势/低位股票占比的中位数；
- 阶段按“明显退潮、退潮观察、强势扩散、低位修复、极端低位、方向未明”的顺序
  匹配，使用 5 日变化、20 日强势参与率峰值及回撤；
- 高置信度要求覆盖率至少 75% 且有效成员至少 20，中置信度要求覆盖率至少 55% 且
  有效成员至少 10，其余为低；历史少于 20 个行业观测或低置信度时阶段关闭为
  “方向未明”。

该方法是可复算的研究假设，不是经独立样本外认证的预测模型，也不是交易信号。

## 数据与点时边界

- 股票价格使用同一快照内的 `adjusted_market.research_close_index`，成交额使用
  `daily_market.amount_thousand_cny`；
- 行业归属按每个评价日的 `[effective_from, effective_to)` 查询，禁止当前成员倒灌；
- 行业注册表来自同一快照的 `industry_taxonomy`，数量不得写死；
- API 在一次请求开始时固定快照身份，不混用运行中切换的 `current`；
- 分类、成员、价格或历史不足时保留行业身份并给出缺口，不把缺失值画在原点；
- 结果仅为可重建投影，不发布第二份数据真相。

## UI 影响

- 行业局部模式扩展为“行业热力 / 生命周期结构 / 相对轮动”；
- 结构地图横轴为 `S`、纵轴为 `L`、气泡面积为近 20 日成交额占比、颜色为阶段、
  描边为置信度；
- 标签只优先显示选中、极值和近期迁移行业，完整身份由可读索引保证；
- 必备状态：Loading、Empty、Stale、Blocked、Error、单行业覆盖不足；
- 窄屏先给出选中结论，地图受控横向查看，索引置于地图下方。

## 验收

1. Given 一个准确不可变快照，When 计算生命周期，Then 每个行业的坐标、阶段、成交额
   占比、成员覆盖和分类身份来自同一截止日。
2. Given 历史归属变化，When 计算过去任一评价日，Then 只使用当日有效成员，不使用
   当前成员回填。
3. Given 行业历史或覆盖不足，When 返回投影，Then 行业仍在索引中并显式不可用，不
   产生 `(0,0)` 坐标。
4. Given 桌面与窄屏浏览器，When 选择、搜索或筛选行业，Then 地图、结论与索引同步，
   且不产生额外提供方请求。
5. Given 任一生命周期结果，When 检查页面和 API，Then 均明确声明研究观察，不是买卖
   信号，且不存在下单入口。

## 检查

```text
uv run pytest tests/unit/test_industry_lifecycle.py \
  tests/integration/test_industry_lifecycle_api.py
pnpm --dir apps/web test
pnpm --dir apps/web typecheck
make e2e-smoke
git diff --check
```

## 受保护边界

本工作包只授权本地只读市场研究。它不批准行业内个股排序、ETF 策略晋级、券商连接、
Shadow、Paper、Live 或任何订单动作。

## 完成记录

- 正式快照：
  `snapshot:sha256:b9d18ef490c98dc02f1db0d3ac36d62c2b2458a4fb1bec79b0d6419da0f24980`；
- 证据截止 2026-07-28，注册表 31 个 SW2021 L1；30 个行业达到坐标最低覆盖，1 个
  行业保留身份并显式低覆盖，不放入原点；
- 当前阶段分布为：方向未明 15、低位修复 9、极端低位 4、退潮观察 2、强势扩散 1；
  30 个行业高置信度、1 个低置信度；
- 正式冷计算约 5.54 秒；同一不可变快照的进程内重读约 0.3 毫秒，页面/API 请求不
  访问提供方；
- Ruff、Mypy、13 个聚焦 Python 测试、47 个前端测试和 TypeScript 类型检查通过；
- 生命周期专项 Playwright 流程通过，验证 31 行业索引、单次生命周期请求、无交易
  按钮和窄屏无页面级溢出；
- 正式桌面与窄屏截图：
  `var/evidence/wp-0040-industry-lifecycle.png`、
  `var/evidence/wp-0040-industry-lifecycle-mobile.png`；
- 全量浏览器烟测首次运行时，本机资源争用令既有大盘用例在 5 秒断言窗口内仍处于
  Loading；该次全量运行未记为通过。清理本包临时进程后，生命周期专项流程独立重跑
  通过；
- `check_repository.py` 不再新增文件/函数阻断；仓库仍有两个与本包无关的既有脚本
  超过函数阻断阈值。
