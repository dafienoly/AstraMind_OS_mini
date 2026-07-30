# WP-0041：MiniQMT 数据源路由、实时管线与测速门禁

- 状态：实施中；架构、真实全能力探测、100 次/分钟 Tushare 基准、快速生产范围
  门禁及用户批准的两类日线成本例外切源已完成；实时 15 分钟盘中验收、财务字段
  单位门禁与扩展数据集原子发布待完成
- 需求：REQ-2026-0004 v2.2.0
- ADR：ADR-0004、ADR-0009
- 阶段：2C、2F
- UI：后端不适用；市场页视觉改动需另行更新并批准 UI 提案
- 授权：仅 MiniQMT 行情与资料；不读取账户、不委托、不撤单

## 目标

建立提供方中立的规范数据集端口、版本化逐数据集路由、整批回退、常驻 MiniQMT
只读桥、真实测速门禁，以及可供市场界面消费的 1 秒实时投影和 SSE。

## 已实现

- `CanonicalDatasetRequest`、`ProviderBatch`、`DatasetSourceRoute`、
  `SourceSelectionEvidence`、`ProviderBenchmarkReport`；
- Tushare 与 MiniQMT 批量适配器、旧日度管线兼容门面、来源路由策略和追加式选源
  证据；
- 主源失败时整批回退，原始失败响应保留；原始记录、规范观察和清单使用实际来源；
- Windows Python 3.11 常驻 NDJSON 桥，固定 XtQuant 路径、行情端口、客户端指纹，
  只导入 `xtquant.xtdata`；
- WSL 启动前有限探测最新 Interop socket，陈旧 socket 在短超时后跳过，不关闭或
  重启 WSL；桥返回精确 Windows 进程号，请求超时只终止该桥进程树并允许重连，不
  遗留继续占用行情端口的孤儿进程；日度空证券池请求在桥内冻结为 `沪深京A股`
  当前列表；
- L1 五档、昨收、交易状态与接收时间规范化；队列溢出、断线和大帧失败关闭；
- 1 秒宽基/广度/行业当前投影、全 A 股长期 1 分钟聚合、5 个交易日原始与规范化
  细粒度负载留存及永久删除台账；一秒聚合不长期保存；
- `/api/market/realtime` 与 `/api/market/realtime/stream`；
- 财务长表、十大股东、指数权重、当前板块成员和合约快照的点时契约与规范化；
- 同口径 P50/P95/P99、吞吐、覆盖和值差异测速命令。

## 真实探测与诊断测速

2026-07-29 已恢复 WSL/Windows Interop，并使用隔离的 Windows Python 3.11 环境完成
真实只读探测。股票/宽基日线、1 分钟 K 线、合约资料、交易日历、指数权重、板块
目录与成员、五类财务表、股东户数、十大股东和十大流通股东均返回有效数据；当前
公司行动因子窗口为空。L2、逐笔、北向、ETF IOPV/申赎、公告问答和 IPO 仍登记为
`unsupported`。

Tushare 按用户指定的 100 次/分钟作为速度基准。最初 30 次热缓存诊断确认
MiniQMT 的方向性优势；改用矩阵批量读取并补齐原生 `preClose` 后，3 次快速诊断结果
如下：

| 数据集 | MiniQMT P50 | MiniQMT P95 | Tushare P50 | Tushare P95 |
| --- | ---: | ---: | ---: | ---: |
| 股票 20 日日线 | 14 ms | 17 ms | 600 ms | 601 ms |
| 宽基 20 日日线 | 19 ms | 20 ms | 601 ms | 608 ms |

两类诊断样本的主键、OHLC、成交量和成交额门禁均通过；诊断报告不能激活生产路由。
MiniQMT 其他热缓存 P95：1 分钟 K 线 12.71 ms、合约资料 1.01 ms、指数权重
15.27 ms、板块目录 78.52 ms、三类指数板块成员 156.09 ms、资产负债表
27.37 ms、股东户数 3.47 ms、十大股东 16.87 ms、十大流通股东 17.44 ms。

快速相对测速接受现有提供方缓存，不追求精确 P99。矩阵批量读取把全市场单日的
MiniQMT 端到端时间从约 6.8 秒降至约 1.5 秒；500 只近 20 个交易日约 0.65 秒，
而当前 Tushare 历史请求在 100 次/分钟下需要 500 次调用，理论下限约 300 秒。
因此 MiniQMT 适合批量历史、实时和资料路径，但不能据此推导所有日度数据集都应切源。

## 生产门禁

数据集只有在完整生产范围达到以下条件时才更新路由策略：

- 主键覆盖 100%、无重复和范围外记录；
- 日线价格误差不超过 `max(0.001 元, 1bp)`，量额误差不超过 0.1%；
- 财务报告期、公告日、修订和单位完整；
- P95 至少快两倍，吞吐至少两倍，错误率不升高；
- 默认切源前发布完整单源基线；用户批准的日期切源必须冻结提供方时间谱系，禁止同日
  混源和跨边界单请求。

小样本测速只生成候选证据，不授权生产切源。真实门禁通过后直接切换，不再设置按
交易日观察期；回退只能发生在当前日期所属的提供方时期内。

2026-07-29 快速生产范围报告
`sha256:2f23c22c50563d4af58dc67af073ddddf6ee711deedb774fdce6281fabcba4e0`
给出以下路由结论：

- `daily_market`：5524/5524 主键覆盖，但 `920008.BJ` 的成交量和成交额口径不一致；
  MiniQMT P95 约 1.48 秒，Tushare 按交易日一次取全市场约 0.60 秒，不切源；
- `broad_index_daily`：132/132 主键覆盖，MiniQMT P95 约 27 ms，Tushare 约
  3.62 秒；深证成指和创业板指的成交量/成交额语义不一致，不切源；
- 个股 20 日诊断样本和宽基 OHLC 样本质量通过，但不能覆盖上述完整生产范围失败。

用户随后明确选择免费成本优先，批准两个数据集在保留上述未通过项证据后使用
MiniQMT 主源。日期切源生效后的当前策略
`sha256:2c2be55ab0d13a6582418d3e9d909feda2bc7109bc40380130bdeb36bc8100a0`
保留两类适配器，但只按请求所属时期选择一个提供方，质量门版本为
`user-cost-override-20260729`。任何空响应、字段缺失、重复主键、范围外记录或适配器
错误都失败关闭，不得用 Tushare 单行修补 MiniQMT 版本。用户于 2026-07-29 进一步
冻结日期边界：2026-07-28 及以前沿用 Tushare，2026-07-29 起只用 MiniQMT；无需
重抓 MiniQMT 全历史。路由和数据集清单必须记录该 `provider_lineage`。日度发布还
必须以同日 `daily_basic` 证券集合校验 `daily_market` 覆盖；提供方缓存只有部分证券
时，失效当日暂存并整日重取，覆盖不全不得发布 `current`。

2026-07-30 日度运行发现 MiniQMT 本地日线缓存不会因读取自动更新。单日请求现先
读取目标日缓存，只对缺失证券按 100 只一批调用只读
`download_history_data2`，随后重新读取并执行原有整日覆盖门禁；已完成批次可在同一
运行恢复时复用。`daily_market` 与 `broad_index_daily` 的单路由预算调整为 600 秒，
仍受日度任务 35 分钟总预算约束，且不允许跨日期谱系回退到 Tushare。日度状态投影
使用的交易日历同时截断到目标日，禁止把提供方重试窗口中的未来交易日发布进目标日
`daily_tradability`。

新实时、当前资料、财务和股东数据集仍按各自覆盖、点时和单位门禁独立推进。

## 检查

```text
uv run pytest tests/unit/test_source_router.py
uv run pytest tests/unit/test_source_quality.py
uv run pytest tests/unit/test_miniqmt_normalization.py
uv run pytest tests/unit/test_realtime_projection.py
uv run pytest tests/integration/test_realtime_market_api.py
make miniqmt-source-benchmark PROVIDER_ENV_FILE=... REPETITIONS=30
uv run python scripts/benchmark_market_data_sources.py \
  --provider-env-file ... --coverage-scope production \
  --universe-file var/data/benchmarks/production-universe-20260728.txt \
  --repetitions 3 --cache-state warm --performance-only --quick
make miniqmt-realtime DURATION_SECONDS=900
```

真实命令只读取行情/资料，不进入默认 `make check`，输出固定
`broker_actions_allowed=false`。
