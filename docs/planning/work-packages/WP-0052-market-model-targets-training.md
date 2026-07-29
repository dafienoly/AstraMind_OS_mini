# WP-0052：五类市场模型目标、估计器与研究目标规则

- 版本：1.0.0
- 状态：已完成（计算内核；生产特征/证据和激活尚未执行）
- 需求：REQ-2026-0002 v1.9.0、REQ-2026-0008 v2.0.0
- 阶段：6I
- UI 提案：不适用；本包不修改用户界面
- 分支/工作区：`codex/current-work-checkpoint-20260728`
- 券商授权：无

## 目标

实现五类 v2 的无前视标签、固定 HistGradientBoosting 训练器、验证指标、预测批次身份
以及 ETF 只读目标草案权重规则，为后续真实特征构建和证据回放提供可测试计算内核。

## 非目标

- 不从生产快照构建完整历史训练矩阵；
- 不激活模型或替换现有 v1 页面；
- 不创建公共 `PortfolioTarget`、`OrderPlan` 或委托；
- 不修改 React/CSS/路由；
- 不连接 MiniQMT 账户或交易端口。

## 允许文件

- `src/astramind_mini/strategy_research/market_models/**`
- `tests/unit/test_market_model_targets.py`
- `tests/unit/test_market_model_training.py`
- 本工作包与直接追踪文档

## 高争用文件

- `src/astramind_mini/strategy_research/public.py`
- `docs/requirements/README.md`

## 上下文与契约

- Strategy Research 唯一拥有标签、估计器和预测批次；
- 复用 WP-0050/0051 的模型清单、点时样本、切分、产物和激活契约；
- Market Regime 尚不导入本包内部模块，后续只消费公共预测契约；
- ETF 输出仍是研究目标草案语义，不进入 Portfolio & Risk。

## 数据与点时影响

- 所有目标由调用方提供的未来窗口构造，特征截止与标签终点必须由点时样本契约校验；
- 行业、市场和官方 ETF 基准收益必须来自同一快照和同一执行时钟；
- 学习特征允许 `NaN` 表示缺失，但拒绝无穷值和“缺失填零”；
- HistGradientBoosting 关闭内部随机 early stopping，模型选择只使用显式时间折。

## 验收

1. 热力 1/5 日、相对轮动 5/20 日超额目标可复算；
2. 生命周期六阶段按冻结优先级唯一标注；
3. 行业排序 20/60 日目标与 `n/(n+10)` 收缩公式准确；
4. ETF 20 日成本后官方基准超额与相关性/逆波动权重准确，最多两只、单只 35%、
   总暴露 60%；
5. 回归使用时间折 RankIC，分类同时报告 Macro-F1 与 Brier；
6. 训练矩阵缺失保持 NaN，无穷值、样本错位或无有效折失败关闭；
7. 预测批次绑定模型、数据、特征、截止、周期和内容哈希，券商动作 false。

## 检查

```text
uv run pytest tests/unit/test_market_model_targets.py \
  tests/unit/test_market_model_training.py
uv run ruff check src/astramind_mini/strategy_research/market_models \
  tests/unit/test_market_model_targets.py tests/unit/test_market_model_training.py
uv run mypy src/astramind_mini/strategy_research/market_models
git diff --check
```

## 受保护边界

本包只形成只读研究计算。任何生产激活、ETF 策略晋级、组合、Paper/Live 或券商动作
继续需要独立证据和授权。

## 实施结果

- 热力/相对轮动同基准超额、生命周期六阶段优先标签、行业排序 20/60 日混合目标与
  小行业收缩公式已实现；
- ETF 官方基准成本后超额、相关性大于 0.85 去重、最多两只、逆波动、总暴露 60%、
  单只 35% 和现金余量已实现；
- 训练矩阵原生保留 NaN、拒绝无穷值，HistGradientBoosting 关闭内部随机 early
  stopping，只使用显式时间折选参；
- 回归时间折报告 Spearman RankIC，生命周期分类同时报告 Macro-F1 与多类 Brier；
- 新增内容寻址 `MarketPredictionBatch`，严格区分回归/分类记录并固定券商动作 false；
- 27 个市场模型契约、底座、目标和训练测试通过，Ruff、Mypy 与
  `git diff --check` 通过；
- 未读取生产训练矩阵、未激活模型、未修改 UI，也未产生组合或券商动作。
