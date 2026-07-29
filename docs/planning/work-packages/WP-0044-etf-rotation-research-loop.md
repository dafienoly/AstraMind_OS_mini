# WP-0044：ETF 轮动研究闭环

- 状态：功能与自动化验收完成；真实浏览器截图受本机企业网络策略阻断
- 需求：REQ-2026-0008 v1.10.0
- 阶段：6E、6F
- UI：UI-PROP-0009 v0.2（已批准）
- 授权：ETF 轮动研究公式、候选冻结回放、研究目标草案和只读界面

## 目标

从一个准确 `DataSnapshot` 形成可解释的 ETF 方向漏斗、价格核验、失败关闭的回放状态
和研究目标权重，并按已批准提案在“市场 → ETF 轮动”展示真实结果。

## 非目标

- 不创建公共 `PortfolioTarget`、`OrderPlan` 或委托数量；
- 不连接 MiniQMT，不运行 Research Shadow、Paper 或 Live；
- 不把 OHLC 价差代理称为真实 bid/ask；
- 不把相对申万 L1 的暴露偏离称为基金官方基准跟踪误差；
- 不把 2026-07-29 前的当前映射回放称为当时已知或样本外证据。

## 首版公式

公式版本为 `etf-rotation-research-v1.0.0`，周五收盘形成判断，假设下一交易日开盘
执行；日度只重算陈旧与可交易性状态。

综合分：

```text
score = 0.35 × lifecycle
      + 0.30 × relative_strength
      + 0.20 × price_structure
      + 0.15 × liquidity
```

- 生命周期按“强势扩散/低位修复/方向未明/退潮观察/极端低位/明显退潮”映射为
  `100/75/50/25/10/0`；
- 相对强弱使用 ETF 相对映射申万 L1 的 20 日与 60 日收益差；
- 价格结构使用正 20 日收益、`close > MA20` 和 `MA20 > MA60`；
- 流动性从 20 日成交额中位数 2,000 万元到 2 亿元作有界对数映射。

候选还必须满足：`exact` 映射、252 个完成交易日、规模不低于 1 亿元、综合分不低于
60、价格结构不少于 60、Corwin–Schultz 20 日 OHLC 价差代理不高于 35 bp、相对申万
L1 的 60 日年化跟踪偏离代理不高于 12%。代理种类和缺口必须可见。

## 目标与成本

- 只产生 `EtfTargetDraft`，最多两只、单只 30%、总暴露不超过 60%，其余为现金；
- 当前持仓事实未接入时统一按 0% 当前权重展示，不计算真实调仓指令；
- 回放假设初始研究资金 5 万元，ETF 佣金万 0.5、每笔最低 5 元、单边滑点 20 bp，
  无印花税，并在下一交易日开盘执行；
- 映射登记前、生命周期历史缺失、真实盘口缺失或当前数据陈旧时，回放/目标分别显示
  `candidate_frozen`、`blocked`、`stale`，不得补造绩效。

## 允许文件

- `src/astramind_mini/market_regime/contracts/etf_rotation.py`
- `src/astramind_mini/market_regime/domain/etf_rotation.py`
- `src/astramind_mini/market_regime/adapters/etf_rotation_queries.py`
- `src/astramind_mini/market_regime/adapters/snapshot_etf_rotation.py`
- 对应 Market Regime 导出和 composition 路由
- `apps/web/src/market-dashboard/etf-rotation/**`
- 对应客户端、类型、路由、样式和测试
- `tests/unit/test_etf_rotation.py`
- `tests/integration/test_etf_rotation_api.py`
- `tests/e2e/foundation.spec.ts`
- 本包及直接引用的需求、计划、数据合同、决策日志和追踪索引

## 受影响合同

- `EtfRotationProjection`
- `EtfRotationCandidate`
- `EtfReplaySummary`
- `EtfTargetDraft`
- `EtfTargetWeight`

全部为只读研究合同，不替代 `StrategyVersion`、`PortfolioTarget` 或 `OrderPlan`。

## 验收

1. 公式、参数、代理种类、数据快照和映射版本共同进入投影身份；
2. 未来日线、未来映射和不可用生命周期不得进入当前判断；
3. 陈旧、映射缺失、价差代理异常、跟踪偏离、历史不足和流动性不足分别可见；
4. 历史映射非点时时回放明确阻断或标为候选冻结，不累计晋级证据；
5. 目标草案遵守两只、单只 30%、总暴露 60% 和允许现金；
6. 页面按 UI-PROP-0009 v0.2 展示漏斗、候选、统一蜡烛图、双端范围轴、目标和阻断；
7. 桌面与窄屏浏览器流程、真实截图、刷新恢复和自动化测试通过；
8. API、界面和测试均证明不会产生券商动作。

## 保护边界

本包完成后仍需独立的真实 bid/ask 历史、官方跟踪基准、封存回放区间、Research
Shadow/Paper 晋级和公共组合资金边界。用户在本次对话中的授权不扩展至这些动作。

## 实施结果

- 只读 API、方向漏斗、候选联动、日/周/月蜡烛、双端范围轴、代理披露、回放状态和
  研究目标草案已经实现；
- 正式快照产生 32 个映射方向，但快照 `as_of` 早于映射 2026-07-29 18:00
  可用时刻，因此准确结果为 `blocked`、现金 100%、回放 `candidate_frozen`；
- 后端 Ruff、Mypy、5 项单元/集成测试、公共契约检查，以及前端类型检查、lint、
  2 项组件流程测试和生产构建通过；
- Chrome 对 `127.0.0.1` 的访问被企业网络策略拒绝，桌面/窄屏真实截图未取得。
  该外部验收项不以替代浏览器或规避策略伪造为通过。
