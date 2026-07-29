# WP-0053：市场模型状态投影与只读 API

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0002 v1.9.0、REQ-2026-0008 v2.0.0
- 阶段：6I
- UI 提案：不适用；本包只提供后端状态，不修改用户界面
- 分支/工作区：`codex/current-work-checkpoint-20260728`
- 券商授权：无

## 目标

提供 `GET /api/market/model-status`，统一返回五类模型的准确方法、证据、激活或 v1 回退
状态；在尚未训练或产物无效时如实显示 fallback/blocked，不返回伪造 v2。

## 非目标

- 不训练或激活生产模型；
- 不修改现有市场投影字段或 UI；
- 不创建组合、订单、Research Shadow、Paper 或 Live；
- 不读取 MiniQMT 账户或交易端口。

## 允许文件

- `src/astramind_mini/market_regime/contracts/model_status.py`
- `src/astramind_mini/market_regime/adapters/model_status.py`
- 对应 Market Regime/Strategy Research 公共导出
- `src/astramind_mini/composition.py` 最小 GET 路由接线
- `src/astramind_mini/config.py` 模型制品目录配置
- `tests/unit/test_market_model_status.py`
- `tests/integration/test_market_model_status_api.py`
- 本工作包与直接追踪文档

## 高争用文件

- `src/astramind_mini/composition.py`
- `src/astramind_mini/config.py`
- 两个上下文 `public.py`
- `docs/requirements/README.md`

## 上下文与契约

- Strategy Research 公共导出只读 `ModelActivationStore` 和激活契约；
- Market Regime 拥有页面状态投影，不读取训练器内部对象；
- composition root 只负责把本地模型目录接入 GET API；
- 新增 `MarketModelStatusProjection` 和 `MarketModelStatusItem`。

## 验收

1. 无任何 v2 激活文件时，五类模型全部返回准确 v1 与 `v2_not_trained`；
2. 一个合法 `unvalidated_v2` 激活只改变对应家族，其他家族不受影响；
3. 当前指针/历史内容损坏时该家族失败关闭为 v1，并显示稳定原因；
4. 响应含准确方法、清单、证据、时间、状态和券商 false；
5. API 不访问数据提供方、MiniQMT 账户或交易端口。

## 检查

```text
uv run pytest tests/unit/test_market_model_status.py \
  tests/integration/test_market_model_status_api.py
uv run ruff check src/astramind_mini/market_regime \
  tests/unit/test_market_model_status.py tests/integration/test_market_model_status_api.py
uv run mypy src/astramind_mini/market_regime
git diff --check
```

## 受保护边界

状态 API 只是只读解释层。`active_v2` 也不表示策略晋级、可交易资格或券商授权。

## 实施结果

- 新增 `MarketModelStatusProjection` / `MarketModelStatusItem` 和
  `GET /api/market/model-status`；
- 当前没有生产 v2 激活，真实 API 因而为五类模型分别返回准确 v1、
  `fallback_v1`、`blocked` 与 `v2_not_trained`；
- 单家族 `unvalidated_v2` 不影响其他家族，当前指针或历史内容损坏会失败关闭为 v1；
- API 响应和激活契约均固定券商、组合、订单权限 false，不访问提供方或账户；
- 31 个市场模型聚焦测试、Ruff、Mypy 和 API 集成检查通过；
- 仓库检查仅被本包前已存在/并行增长的 `tests/e2e/foundation.spec.ts` 503 行阻断
  （阈值 500）；本包未修改该文件；
- 未修改 UI、未训练/激活生产模型，券商动作保持为零。
