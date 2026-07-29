# WP-0051：市场模型点时样本、训练切分与安全产物底座

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0002 v1.9.0、REQ-2026-0008 v2.0.0
- 阶段：6I
- UI 提案：不适用；本包不修改用户界面
- 分支/工作区：`codex/current-work-checkpoint-20260728`
- 券商授权：无

## 目标

建立五类市场模型共用的固定训练配方、标签成熟切分、点时样本门、内容寻址安全模型
产物和只读激活存储，使后续模型不重复实现时间切分、身份和回退规则。

## 非目标

- 不构造五类业务特征或训练生产模型；
- 不采集 MiniQMT 账户或提交订单；
- 不修改 React/CSS/路由；
- 不把 2021 年前 SW2021 回溯成员加入封存证据；
- 不自动把市场模型变成策略版本。

## 允许文件

- `src/astramind_mini/strategy_research/market_models/**`
- `tests/unit/test_market_model_foundation.py`
- `pyproject.toml`、`uv.lock`
- 本工作包与直接追踪文档

## 高争用文件

- `pyproject.toml`
- `uv.lock`
- `src/astramind_mini/strategy_research/public.py`
- `docs/requirements/README.md`

## 上下文与契约

- Strategy Research 唯一拥有模型配方、训练切分、产物和激活记录；
- 复用 `DataSnapshot`、`FeatureSnapshot`、`PredictionBatch` 和 WP-0050 公共契约；
- 新增内部纯规则：`MarketModelRecipe`、`PointInTimeSample`、`WalkForwardFold`；
- 不增加 Market Regime 对 Strategy Research 内部模块的依赖。

## 数据与点时影响

- 切分先按标签成熟截止裁剪，再创建月度、最近 12 个标签完成月 walk-forward 验证；
- 每个样本显式记录特征时间、成员知识状态、标签终点和可用时间；
- `sealed_replay`、`audit`、`prospective` 一律拒绝
  `reconstructed_not_then_known`；
- 模型产物使用 `skops` 安全格式、SHA-256 内容身份和受信类型白名单读取，不用 pickle。

## 验收

1. 五类配方准确固定窗口、周期、模型类型、网格和种子；
2. 标签未成熟样本永远不进入训练或验证；
3. 2021 年前回溯成员不能进入封存/审计/前向折；
4. 相同输入产生相同折身份、模型清单和产物哈希；
5. 产物内容或清单哈希不一致时读取失败关闭；
6. 只读激活落盘原子更新，历史记录只追加，v2 损坏时可明确解析为 v1 回退；
7. 券商、组合和订单授权始终为 false。

## 检查

```text
uv run pytest tests/unit/test_market_model_contracts.py \
  tests/unit/test_market_model_foundation.py
uv run ruff check src/astramind_mini/strategy_research/market_models \
  tests/unit/test_market_model_foundation.py
uv run mypy src/astramind_mini/strategy_research/market_models
git diff --check
```

## 受保护边界

本包只实现本地只读研究基础设施。它不授权生产模型激活、Research Shadow、MiniQMT
Paper/Live、账户读取或券商写入。

## 实施结果

- 锁定 scikit-learn 1.9、skops 0.14 和 NumPy 2.x 的 Python 3.12 依赖；
- 五类配方、16 组固定参数、3/5/10 年滚动窗和 12 个标签完成月已进入纯规则模块；
- 点时样本显式拒绝未成熟标签，封存/审计/前向证据拒绝
  `reconstructed_not_then_known`；
- walk-forward 折、最终训练样本、模型清单和只读激活身份均为确定性内容身份；
- 模型产物使用 skops 内容寻址落盘，读取时拒绝未受信类型并复验哈希；激活历史只追加，
  当前指针原子替换；
- 12 个治理/底座测试、Ruff 与 Mypy 通过；全仓需求顺序测试仍被本包前已存在的
  `WP-0002C` 未进入唯一追踪表阻断，本包新增 WP-0050/0051 均已正确登记；
- 未训练或激活生产模型，未修改 UI，券商动作保持为零。
