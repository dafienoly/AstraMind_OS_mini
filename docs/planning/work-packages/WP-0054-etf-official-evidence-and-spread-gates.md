# WP-0054：ETF 官方证据、真实价差与数据门禁

- 版本：1.0.0
- 状态：已完成（真实价差门按自然交易日继续积累）
- 需求：REQ-2026-0008 v2.0.0
- 阶段：6I
- UI 提案：不适用；本包不修改用户界面
- 分支/工作区：`codex/current-work-checkpoint-20260728`
- 券商授权：无；仅复用已批准的 MiniQMT 只读 L1 行情

## 目标

为 ETF v2 建立可审计的官方跟踪指数、NAV、指数日线和真实 L1 分钟价差事实，并把
点时映射、官方基准、NAV/可交易性及前向 60 个交易日价差冻结为独立数据门。

## 非目标

- 不用 OHLC、成交额或未来抓取补造历史 bid/ask；
- 不把当前查询到的 ETF—指数关系倒灌为历史已知映射；
- 不训练、激活或展示 ETF v2；
- 不创建 `PortfolioTarget`、`OrderPlan`、Research Shadow、Paper 或 Live；
- 不连接 MiniQMT 账户或调用交易端口。

## 允许文件

- `src/astramind_mini/data/etf_model_evidence/**`
- `src/astramind_mini/data/etf_foundation/__init__.py` 的最小公共导出
- `scripts/publish_etf_model_evidence.py`
- `scripts/run_miniqmt_realtime_pipeline.py` 的真实 ETF 价差只读接线
- 对应数据契约、需求追踪、单元与集成测试

## 高争用文件

- `scripts/run_miniqmt_realtime_pipeline.py`
- `docs/requirements/README.md`
- `docs/data/data-contracts.md`

## 数据与点时影响

- `etf_basic` 的当前官方映射按实际检索时间可用；在未取得历史公告证据前，
  `historical_availability_known=false`，不能进入 2024—2025 封存证据；
- NAV 使用 `ann_date` 作为市场可用日，缺失公告日时按检索时间失败关闭；
- 指数日线按交易日收盘后可用，原始提供方响应与规范化观察分开保存；
- 原始 MiniQMT L1 继续进入既有不可变微批；本包只追加按会话、分钟聚合的 ETF
  bid/ask 中位数和 P90，不建立第二套行情真相；
- 60 日窗口必须来自登记后的连续开放交易日，至少 54 日达到 216/240 个计划分钟，
  窗口分钟价差中位数不高于 15 bp、P90 不高于 35 bp。

## 验收

1. 28 只登记 ETF 都能得到提供方明确的官方指数代码和名称；缺失或重复时阻断；
2. NAV 公告日、指数日线和原始响应可追溯，不能把检索日伪装成历史公告日；
3. 无效、倒挂或零 bid/ask 不进入有效价差，分钟统计身份可复算；
4. 不足 60 个连续开放交易日、日覆盖不足或价差超限分别返回稳定阻断原因；
5. 实时服务只消费已登记 ETF 的 L1，原始微批、市场投影和 ETF 价差共享同一会话；
6. 当前数据门准确保持 `blocked`，不得因代码完成而伪造 60 日证据。

## 受保护边界

数据发布和真实价差积累只是只读研究数据。任何模型激活、公共组合、券商账户访问和
交易动作继续需要其各自的证据与授权。

## 实施结果

- 正式发布并激活 DataSnapshot
  `snapshot:sha256:b4d8bfe0889efd77bd4171773c502d1619ca07b3767e8508be69f66111e68ca5`；
- 已保存 28 条官方 ETF—指数身份、46,504 条 NAV 和 112,468 条
  2010-01-04～2026-07-29 官方指数日线；提供方原始响应独立留存；
- 首次发布遇到 `930608.CSI` 历史开盘为 0 时失败关闭，随后以显式 `null` 保存
  缺失 OHLC，未填造价格；
- MiniQMT 常驻任务已加载 ETF 价差分钟投影；原始 L1 仍由既有微批保存，价差只从
  下一有效交易会话向前积累；
- 当前官方映射历史可用时点未知且真实价差为 0/60 个交易日，ETF v2 准确保持
  `blocked`；
- 6 个 ETF 官方证据/价差聚焦测试、Ruff 和 Mypy 通过，券商动作始终为零。
