# WP-0050：市场研究 v2 治理、身份与视觉提案

- 版本：1.0.0
- 状态：已完成（治理、公共契约与视觉提案；UI 未获准确批准）
- 需求：REQ-2026-0002 v1.9.0、REQ-2026-0008 v2.0.0
- 阶段：6I
- UI 提案：UI-PROP-0012 v0.1（待准确批准；本包不修改 React/CSS）
- 分支/工作区：`codex/current-work-checkpoint-20260728`
- 券商授权：无

## 目标

冻结五类市场研究 v2 的方法、点时窗口、证据门、模型身份与只读激活边界，建立公共
模型治理契约，并提交可单独批准的界面增量示意图。

## 非目标

- 不在 UI-PROP-0012 v0.1 获准确批准前修改 React、CSS、路由或可见文案；
- 不训练或激活生产模型，不宣称当前结果已通过封存样本外验证；
- 不倒灌 2021 年前 SW2021 回溯成员作为当时已知事实；
- 不创建 `PortfolioTarget`、`OrderPlan`、Research Shadow、Paper、Live 或委托；
- 不连接 MiniQMT 账户或交易端口。

## 允许文件

- `docs/adr/0012-separate-readonly-market-model-activation.md`
- `docs/ui/proposals/0012-market-model-evidence-overlay/**`
- 本工作包直接引用的需求、数据契约、阶段计划、决策记录与文档索引
- `src/astramind_mini/strategy_research/market_models/contracts.py`
- `src/astramind_mini/strategy_research/public.py`
- `tests/unit/test_market_model_contracts.py`

## 高争用文件

- `docs/requirements/README.md`
- `docs/planning/phased-implementation-plan.md`
- `docs/data/data-contracts.md`
- `src/astramind_mini/strategy_research/public.py`

## 上下文与契约

- Data：继续拥有原始/标准化观察、可用时间和不可变 `DataSnapshot`；
- Strategy Research：拥有模型清单、训练、证据、产物和只读激活记录；
- Market Regime：只消费公共预测与激活状态，和原始证据一起形成页面投影；
- 新增公共契约：`MarketModelManifest`、`MarketModelEvidenceBundle`、
  `ModelValidationSummary`、`ModelActivation`、`ModelPredictionContext`；
- 兼容性：现有 v1 投影和 API 字段保持可读，v2 使用独立方法身份。

## 数据与点时影响

- 热力/相对轮动开发期截至 2022，封存回放为 2023—2025，2026 只作审计；
- 生命周期/行业排序开发期为 2021—2023，封存回放为 2024—2025；
- ETF 开发期为 2021—2023，只有点时映射、官方基准和 NAV 可验证时才允许使用
  2024—2025 封存窗口；真实 L1 价差只从采集登记后向前积累；
- SW2021 的 2021 年前成员回溯带 `reconstructed_not_then_known`，不得进入封存证据。

## UI 影响

- 用户可见变化只由后续 UI 工作包按准确批准的 UI-PROP-0012 实施；
- 本包只提交“方法与证据带”桌面/窄屏示意，覆盖 Loading、Empty、Stale、Blocked、
  Error、Disconnected、Unvalidated 与 Fallback；
- 截图目标：1440×900 与 390×844。

## 风险与授权

市场模型激活只是只读页面方法指针，不能复用策略晋级权限。自动回退只回到准确 v1
研究投影，不触发减仓、卖出或任何券商动作。

## 验收

1. Given 任一 v2 模型，When 记录预测或证据，Then 可追溯到准确数据、特征、模型、
   代码、参数、窗口和内容哈希。
2. Given v2 证据不支持或产物损坏，When 解析激活状态，Then 显式回到准确 v1 并保留
   原 v2 记录，不改写历史。
3. Given 2021 年前 SW2021 回溯成员，When 构建封存样本，Then 记录并阻断，不把它
   作为当时已知成员。
4. Given UI-PROP-0012 尚未准确批准，When 完成本包，Then 仓库没有由本包产生的
   React/CSS/路由变化。
5. Given 任一模型治理记录，When 检查授权字段，Then 券商、组合和订单能力均为 false。

## 检查

```text
uv run pytest tests/unit/test_market_model_contracts.py
uv run python scripts/check_repository.py
git diff --check
```

## 交接

- UI 精确批准前只继续后端、数据、模型和证据工作；
- UI-PROP-0012 v0.1 获批后，后续独立 UI 工作包才允许修改可见页面；
- 不执行模型生产激活、MiniQMT 账户、Paper/Live 或交易动作。

## 实施结果

- ADR-0012 已冻结只读市场模型激活与策略晋级分离；
- 五类模型、时间窗、证据门、ETF 真实数据门和 v1 回退进入 REQ-0002 v1.9.0 与
  REQ-0008 v2.0.0；
- 新增九类严格公共契约，并通过 5 个正向/负向单元测试、Ruff、Mypy、仓库文档/SVG/
  密钥检查和 `git diff --check`；
- UI-PROP-0012 v0.1 已形成可审阅 SVG，状态保持 `awaiting_user_approval`；
- 本包未修改 React/CSS/路由，未训练或激活生产模型，券商动作保持为零。
