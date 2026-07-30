# 本地开发指南

> 2026-07-29 起，文中已有 `shadow` 命令和制品只作为 Local Replay 兼容测试资产；
> 保留旧命令名是为了历史兼容，不代表它就是 REQ-2026-0014 新批准的 Research
> Shadow。新的多候选 Research Shadow 和单账户 Paper 虚拟分仓都尚未实施。

- 适用工作包：WP-0001、WP-0002A、WP-0002B
- 当前状态：阶段 1A/1B、1C 价格检查器基线、2A 和 2B 历史行情快照已建立；
  阶段 1D 未开始

## 已验证环境

| 项目 | 选择或结果 |
| --- | --- |
| 操作系统 | WSL2，Ubuntu 26.04 LTS |
| Python | 项目固定 3.12；系统 3.14 不作为项目解释器 |
| Python 管理 | `uv` 0.11 系列，依赖由 `uv.lock` 固定 |
| Node | 24 系列 |
| Node 包管理 | `pnpm` 11 系列，依赖由 `pnpm-lock.yaml` 固定 |
| API | FastAPI |
| Web 工具链 | React、TypeScript、Vite；目前只有开发诊断页 |
| 分析存储 | DuckDB Python API；不要求系统 DuckDB CLI |
| 控制存储 | Python `sqlite3`，已验证 WAL；不要求系统 SQLite CLI |
| 浏览器测试 | Playwright 托管 Chromium |
| ROCm/PyTorch | 尚未就绪，只作为可选诊断，不阻断阶段 1 |

Windows 路径中的 `corepack` 当前存在 CRLF 启动问题。项目直接使用 Volta 提供的
`pnpm`，不依赖该 `corepack`。禁止在 WSL 中执行 `wsl.exe --shutdown`。

## 首次安装

```bash
make bootstrap
make doctor
make check
make e2e-smoke
```

`make bootstrap` 按锁文件建立 `.venv`、pnpm workspace 和 Playwright Chromium。
Token、账户与券商凭据只能放在 Git 排除的 `.env.local` 或进程环境中。

## 日常开发

```bash
make dev
```

该命令只监听 `127.0.0.1`：

- API：`http://127.0.0.1:8010/healthz`
- 非产品诊断页：`http://127.0.0.1:5174`

端口 8000 和 5173 已被同机旧 AstraMind 开发服务占用，因此 Mini 使用独立端口，
避免停止或干扰用户现有进程。

API 热重载只监听 `src/`、`apps/api/` 和 `scripts/` 下的 Python 源码，不监听
`.venv/`、`node_modules/` 或持续写入的 `var/` 数据目录；后台数据管线运行时不会再
因触发整仓扫描而拖慢诊断页。

诊断页只证明 FastAPI、React/Vite 和浏览器链路可用，不代表产品 UI 已实现。

## 稳定检查

- `make doctor`：必需工具或端口失败时返回非零；CLI 与 GPU 缺失只警告。
- `make check`：格式、lint、类型、单元、契约、架构、文档、密钥、规模和构建。
- `make docs-check`：只运行本地链接、SVG、批准记录、密钥和规模等仓库文档检查。
- `make e2e-smoke`：临时启动本地服务，运行可见浏览器流程并清理子进程。
- `make contracts-generate`：公共契约变更后重新生成 JSON Schema。
- `make contracts-check`：验证生成 Schema 与 Pydantic 模型没有漂移。

历史重建、模型训练、Local Replay 和券商探查都不属于这些默认命令。

## 本地运行、备份与恢复

### 日度数据与研究决策链

WP-0030 的首选入口把唯一数据管线、纯本地决策链和当日外部备份收敛为同一运行身份：

```bash
make daily-run \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  TARGET_DATE=YYYY-MM-DD
make daily-run-status
```

提供方尚未完整时保持 `waiting_provider`，不推进研究链，也不切换上一份完整
`DailyRunSummary`。中断或阻断恢复必须复用状态输出中的准确 `run_id`：

```bash
make daily-run-recover \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  RUN_ID=daily-run:<identity>
```

首次成功会在已配置的仓库外目录创建或复用目标日完整备份，再以内容身份发布不可变摘要。
重复运行直接返回同一摘要；并发实例只显示租约占用。三个命令均永久排除 MiniQMT
账户/交易、Paper/Live 和活动前向周期推进；数据步骤可按已发布路由读取 MiniQMT
只读行情。

### Windows 日度计划任务

WP-0031 用 Windows Task Scheduler 唤起 WSL 内的 WP-0030 统一入口。先生成可审查
定义，不会安装任务：

```bash
make daily-schedule-preview \
  PROVIDER_ENV_FILE=/home/ly/work/AstraMind_OS_mini/.env.local
make daily-schedule-status
```

固定触发点为每日 08:30、16:35、16:50、17:10、20:10，以及 Windows 登录后的
错过窗口恢复。20:10 用于在 ETF 日线 18:00 可用、事件输入 20:05 可用后完成同一
运行身份的最终恢复。
决策器读取版本化交易日历；登录恢复只处理最近一个未完成交易日。任务定义只保存环境文件
路径，不复制 Token，并固定输出 `broker_actions_allowed=false`。

实际安装前必须逐字确认预览中的任务名称和仓库目录：

```bash
make daily-schedule-install \
  PROVIDER_ENV_FILE=/home/ly/work/AstraMind_OS_mini/.env.local \
  CONFIRM_TASK_NAME="AstraMind OS Mini - Daily Ops" \
  CONFIRM_WORKDIR="/home/ly/work/AstraMind_OS_mini"
```

任务使用内置 Users 组而不把个人账户标识写入定义；因此首次安装可能出现 Windows UAC
提示。批准 UAC 只用于登记任务，任务本身仍以 `LeastPrivilege` 运行。
任务动作通过 `/bin/bash -lc` 进入 WSL，确保 Task Scheduler 的非交互环境能够解析
用户级 `uv`；直接以 `/usr/bin/make` 作为 WSL 进程会因 PATH 缺少 `uv` 而失败。
2026-07-29 已将已安装任务的环境来源从已不存在的
`/mnt/e/work/AstraMind_OS/.env` 原位更新为仓库内 `.env.local`；随后按 v1.3
重新安装任务并增加 20:10 最终恢复触发。任务名、权限和工作目录未变。

暂停和卸载只改变 Windows 任务状态，不删除快照、控制台账或运行摘要：

```bash
make daily-schedule-pause
make daily-schedule-uninstall
```

系统页和“今日”页读取同一个 `GET /api/system/daily-operations` 持久投影。恢复按钮只向
`POST /api/system/daily-run-requests` 幂等登记本地请求，HTTP 请求本身不访问提供方、
不重算研究链，也不连接 MiniQMT。

以下两个分段入口继续作为诊断和精确恢复工具。目标日期必须是准备核验的交易日：

```bash
make daily-data-update \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  TARGET_DATE=YYYY-MM-DD
make daily-data-status
```

数据提交完成后运行纯本地决策链：

```bash
make daily-decision-run
make daily-decision-status
```

该命令生成 `FeatureSnapshot → PredictionBatch → PortfolioTarget → Local Replay OrderPlan`
和 Local Replay/Paper 就绪预检。它不连接 MiniQMT，不启动活动 Paper 周期，不提交或撤销
模拟盘订单。正常输出必须包含：

```text
paper_dispatch_state=disabled
broker_connection_attempts=0
broker_write_attempts=0
broker_actions_allowed=false
```

系统页只读显示上述两条状态；刷新页面不会触发 Tushare、研究计算或券商调用。

WP-0015 使用显式命令，不启动常驻调度器。盘后窗口决策示例：

```bash
make ops-plan \
  TRADING_DATE=2026-07-28 \
  NEXT_TRADING_DATE=2026-07-29 \
  OPS_AT=2026-07-28T16:35:00+08:00 \
  PROVIDER_COMPLETE=true
```

实际备份前，在 `.env.local` 或进程环境设置一个仓库与 `var/` 之外的目录：

```text
ASTRAMIND_BACKUP_DIR=<仓库外的本机私有目录>
```

然后执行：

```bash
make ops-backup BACKUP_REASON=daily_close LOGICAL_DATE=YYYY-MM-DD
make ops-recovery-drill BACKUP_ID=local-backup:<identity>
```

备份复制控制、Local Replay 和晋级 SQLite 以及当前数据指针，保留最近 30 日和 12 个月末
恢复点。恢复演练只写入 `var/recovery-drills/`，不会覆盖运行状态。未配置目录、目录在
仓库内、文件篡改或 SQLite 损坏时均失败关闭，且不打印实际备份路径、Token 或账户
标识。备份和恢复健康也不授权 Paper 或 Live。

WP-0023A 增加不连接券商的持续 Paper 离线守护。它自动发现当前 Local Replay 决策链、
最新健康备份/恢复和本地 Paper 投影：

```bash
make paper-offline-guard LOGICAL_DATE=YYYY-MM-DD
make paper-offline-fault-drill LOGICAL_DATE=YYYY-MM-DD
```

守护使用 `var/control/local-ops.sqlite3` 的 SQLite/WAL 租约和检查点，重复启动不会重复
任务，中断后从已完成步骤恢复。故障命令覆盖陈旧数据、外来挂单、Mandate 过期、
`submission_unknown`、回调乱序、重启、重复实例和控制库故障。两个命令都固定输出
`broker_actions_allowed=false`，不启动 Windows runner，也不调用 MiniQMT。

## Paper 离线合同

WP-0016 的 Paper 状态机只通过合成测试运行：

```bash
uv run pytest tests/unit/test_paper_execution_offline.py
```

它不读取 `.env.local` 或账户配置，不启动 Windows 进程，也不连接 MiniQMT。未知提交
只能通过事实查询端口恢复，不能直接重提；离线命令适配器会拒绝所有提交和撤单尝试。
下一步 WP-0017 的模拟盘只读握手仍需单独授权。

## 生产数据快照

生产快照发布是显式联网动作，不属于 `make check`：

```bash
make data-snapshot PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env
```

- 命令只读取旧配置文件中的 Tushare 允许键，不复制或打印 Token；
- 18:00 前选择上一自然日作为上界，再取 SSE/SZSE 最近共同开市日；
- 原始响应、Parquet、清单、当前指针和 SQLite 台账均写入 Git 忽略的 `var/`；
- 达到提供方 6000 行上限、空数据、OHLC 异常、日线缺复权因子或身份未知时失败关闭；
- `make data-snapshot` 仍只发布一个完成交易日，适合日常增量。

历史首次导入使用旧 AstraMind 正式 Silver，只联网补旧数据缺口：

```bash
make data-backfill \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData \
  LEGACY_DATASET_VERSION=a-share-daily-v1-20260724-4e1f5f6ae28d \
  BASE_SNAPSHOT_ID=snapshot:sha256:430fbab6c3fa92ea71f90a4a7e81c05522d5828f3cfc805e09a27b97a17a2780
```

该命令可恢复且完成后幂等，不属于默认 `make check`。

每日指标、涨跌停与停复牌事件使用 H1 快照作为基线：

```bash
make data-backfill-h2 \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData \
  LEGACY_DATASET_VERSION=a-share-daily-v1-20260724-4e1f5f6ae28d \
  BASE_SNAPSHOT_ID=snapshot:sha256:e4971c03b9da6c4a94787136071b72c165f0713cfc983b33ca7630a1fdb023dc
```

H2 同样只补旧发布缺失日期，稀疏停复牌接口允许零行响应但会保存原始证据；已完成
状态重复执行不联网。

历史名称/ST 与逐日可交易状态投影完全本地执行，以 H2 快照为基线：

```bash
make data-backfill-h3 \
  LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData \
  LEGACY_DATASET_VERSION=a-share-daily-v1-20260724-4e1f5f6ae28d \
  BASE_SNAPSHOT_ID=snapshot:sha256:c897081a39ab131286af148632c029a9b24e9aff3c23e94cdeafff8ad99d09c4
```

命令按年度恢复，不需要 `PROVIDER_ENV_FILE`，也不会连接 Tushare 或 MiniQMT。完成后
幂等重跑只校验状态与发布身份。

公司行为与统一派生复权价格以 H3 快照为基线：

```bash
make data-backfill-h4 \
  LEGACY_DATA_ROOT=/home/ly/AstraMindResearchData \
  LEGACY_DATASET_VERSION=a-share-daily-v1-20260724-4e1f5f6ae28d \
  BASE_SNAPSHOT_ID=snapshot:sha256:14e41516ba38e7a80241c2e837ba13788d88e348599df27e90de2e2e610a47a2
```

该命令完全本地执行并按年度恢复。前/后复权价只用于研究兼容，原始 OHLC 才能用于
成交模拟；默认研究价格为按 `pct_chg` 连续累计的无量纲指数。

## 只读提供方探测

提供方探测是显式联网动作，不属于 `make check`：

```bash
ASTRAMIND_MINIQMT_XTQUANT_PATH=/path/to/windows/site-packages \
ASTRAMIND_MINIQMT_QUOTE_PORT=<local-quote-port> \
make provider-probe PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env
```

- 旧 `.env` 只读取 Tushare URL、Token、限流、超时和重试允许键；
- `.env.local` 和当前环境仍有更高优先级；
- MiniQMT runner 在 Windows 临时目录隔离加载 `xtdata`，只调用行情和资料接口；
- 输出只显示客户端身份、能力状态和行数，原始证据写入 Git 忽略的 `var/data/`；
- Windows `xtquant` 二进制当前与 Python 3.11 匹配，不改变项目 Python 3.12；
- L2 默认不探测，账户和交易接口在源码层被排除。

未设置外部配置、解释器/包目录不可用或行情端口断开时，命令失败关闭并保留脱敏
报告。闭市订阅没有新消息记录为 `empty`，不能误报为接口不存在。

## MiniQMT L1 有界采集

WP-0002C 已获授权调用 MiniQMT 行情 RPC；该命令仍只允许行情，不得因 WP-0011
账户读取授权而扩大自身范围：

```bash
make miniqmt-l1-capture CAPTURE_SECONDS=5
```

命令只调用 `xtdata.subscribe_whole_quote` 与退订接口，原始和规范化 gzip 微批写入
Git 忽略的 `var/data/realtime/miniqmt/`。超时或异常会终止 runner；输出不打印真实
行情值。首次真实验收使用 `xtquant_250516`，完成 SH/SZ/BJ 全推与退订。

UI Lab 位于 `http://127.0.0.1:5174/dev/ui-lab`。它只使用合成 Fixture，不读取
实时行情或账户。

## MiniQMT 常驻实时管线与数据源测速

常驻行情桥只导入 `xtquant.xtdata`，不读取账户，不暴露委托、撤单或交易回调。
显式配置固定的 `xtquant` 包目录和行情端口后可运行：

桥启动前会在 1 秒候选超时内选择可用的 WSL Interop socket。陈旧 socket 不再导致
三次相同的无效重试，也不会执行 `wsl.exe --shutdown`。股票日度按交易日请求未显式
传证券池时，桥使用 MiniQMT `沪深京A股` 当前成员冻结本次全市场请求。

```bash
make miniqmt-catalog-probe
make miniqmt-realtime
make miniqmt-source-benchmark PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env
```

目录探针逐项检查日线、分钟线、合约资料、交易日历校验、指数权重、板块目录、五类
财务表、股东户数、十大股东、十大流通股东和公司行动因子；只输出字段、行数和脱敏
状态，原始响应留在 Git 忽略的数据目录。L2、逐笔、北向、ETF IOPV/申赎和公告问答
等当前缺口明确登记为 `unsupported`，不创建空生产数据集。

无时长参数时，实时命令常驻运行，只在上海交易日 08:55–16:05 建立全市场 L1
会话，闭市或休市保持等待；每个交易日和每次断线重连都会换代会话。进程锁阻止
第二实例，运行心跳写入 `var/control/realtime-market-service/status.json`。

一秒市场/行业结果只更新 SSE 消费的当前投影，不长期保存。服务建立只读 feed 前，
先从 `xtquant.xtdata` 热缓存补取当日已完成一分钟 Bar，再以
`证券 + 市场分钟` 与 L1 增量确定性对账；形成中、闭合和封存 Bar 分层记录。断线时
不把形成中分钟冒充闭合分钟，跨会话重叠登记为显式缺口并失败关闭。原始响应、
规范一分钟和封存一分钟均保留最近五个交易日。

原始与规范化微批只在会话微批身份、证券/分钟主键、完整性和内容哈希均可从聚合证据
重算后清理；空的或被篡改的 `aggregation-verified.json` 不授权删除。会话/微批清单、
哈希、缺口和删除台账永久保留。

```bash
make realtime-market-service-status
make realtime-market-service-preview
make realtime-market-service-install
make realtime-market-service-start
```

`status` 用 `installed / not_installed / query_failed` 区分 Windows 计划任务查询，
并分别报告 WSL 进程、feed 会话、当前投影和完成日状态。状态还包含最后成功心跳、
最后消息/微批、退出码、有界轮转日志、逐次重试根因和恢复动作；心跳超过 90 秒或
PID 不存在显示 `stale_process`。查询失败不会覆盖最后已知安装事实，暂停后启动会先
重新启用任务；恢复流程不需要卸载任务。

测速命令记录原生获取、桥接、规范化、落盘和端到端延迟。默认产生诊断报告，不能
激活生产路由；只有完整生产范围的覆盖、点时和内容门禁报告才允许执行配置级切源。
MiniQMT 故障时按整个数据集回退 Tushare，既有不可变快照不会被改写。
速度比较固定使用 Tushare 100 次/分钟基准；本机 `.env` 中更高的生产限额不会改变
测速基线。测速重点是 MiniQMT 的常驻桥热缓存延迟和批量吞吐。

只需判断相对快慢时使用快速生产场景，接受现有 MiniQMT 缓存并重复 3 次：

```bash
uv run python scripts/benchmark_market_data_sources.py \
  --provider-env-file /mnt/e/work/AstraMind_OS/.env \
  --coverage-scope production \
  --universe-file var/data/benchmarks/production-universe-20260728.txt \
  --repetitions 3 --cache-state warm --performance-only --quick
```

该命令包含全市场单日、500 只近 20 日和六宽基近 20 日，只生成相对性能报告。
`--quick` 和 `--performance-only` 均被禁止直接激活生产路由。首次准备全市场历史
缓存必须使用显式 `--prepare-miniqmt-cache`；准备过程分 200 只一批记录进度，
不得把冷下载耗时混入热读取结论。

当前生产源路由中，`daily_market` 和 `broad_index_daily` 按用户批准的成本例外使用
`miniqmt, tushare`。这表示 MiniQMT 整批成功时只发布 MiniQMT 版本；失败时丢弃该批
并由 Tushare 完整重取，不表示逐证券或逐字段补值。

WP-0011 已实现 MiniQMT 有界只读账户与启动对账：

```bash
make miniqmt-account-reconcile
```

先在 Git 忽略的 `.env.local` 中准确配置
`ASTRAMIND_MINIQMT_ACCOUNT_MODE=simulation|live`、
`ASTRAMIND_MINIQMT_ACCOUNT_ID` 和 `ASTRAMIND_MINIQMT_USERDATA_PATH`；账户选择和
userdata 路径均按秘密处理，不要放在命令行或日志中。未配置、模式不明确、任一查询
失败或超时时，命令失败关闭且不发布部分快照。2026-07-28 已用模拟盘配置完成一次
真实只读验收；对账因券商资金、持仓与合成 Shadow 起点不同而按预期保持阻断。该命令
只允许资产、持仓、委托和成交查询；Paper、Live、下单、撤单、订阅和交易回调仍禁止。

WP-0017 已单独获准建立一次短时模拟盘只读回调会话：

```bash
make miniqmt-paper-readonly-handshake
```

该命令在启动前锁定 `simulation`，核对券商精确账号、账户类型和状态，读取完整账户
基线并完成回调订阅与退订。闭市或账户无变化时 `callback_status=quiet` 是有效结果。
本机 `xtquant_250516` 没有返回 `account_classification`，证据会明确记录该缺口。命令
始终冻结新委托，不提供下单或撤单入口。

## 首笔 Paper 金丝雀运行

WP-0021 已实现首笔金丝雀的真实预检与运行命令，但命令不会自动运行。首先只能在已
批准的 2026-07-29 09:35～15:00 窗口内建立新鲜只读基线和准确限价：

WP-0022 v1.1 提供推荐的简化入口。先运行只读预检；它会读取当前不可变授权、完整账户
基线和 L1，但不生成限价提案、订单意图或券商命令：

```bash
make paper-canary-preflight
```

成功输出必须包含 `proposal_count_delta=0`、`order_intent_count_delta=0`、
`broker_write_attempts=0` 和 `broker_actions_allowed=false`。窗口前可返回
`submission_window=upcoming`；过期授权不会被命令自动延长。

行情 runner 最多等待8秒获取一条年龄不超过3秒的新 L1 tick；3秒阈值没有放宽。
脱敏 stdout/stderr 位于 `var/control/paper-canary/runner-diagnostics/`。常见阻断为：

- `windows_interop_unavailable`：WSL 调用 Windows 程序的互操作通道不可用；
- `qmt_not_connected`：QMT 行情或交易会话未连接；
- `canary_quote_stale`：等待期耗尽仍没有不超过3秒的 tick；
- `invalid_runner_json`：Windows runner 没有返回有效 JSON；
- `canary_quote_timeout` 或 `paper_readonly_handshake_timeout`：对应 runner 超时。

预检通过后，只能按当前授权记录允许的启动和提交窗口运行：

```bash
make paper-canary-run
```

命令最多等待至09:35，自动建立账户基线和限价提案，然后要求逐字输入类似
`批准 605208.SH 买入100股 限价12.34，仅提交一次` 的动态确认文本。确认通过后自动
创建2分钟批准、执行唯一提交并每5秒查询状态。重启同一命令会发现既有意图并只恢复
监控；不会重新提案或提交。09:44仍有剩余委托时命令提示准确撤单文本，直接回车表示
不撤单。

15:00 后无需复制任何身份：

```bash
make paper-canary-settle
```

命令自动发现唯一 Approval/Intent，查询最终券商事实并生成盘后收敛报告。以下分步
命令继续保留作诊断和异常恢复工具，不作为首选日常入口。

```bash
make paper-canary-stage-limit
```

输出必须完整展示 `605208.SH`、买入、100股、确切限价、最大金额、行情时间、账户
基线、Mandate、PortfolioTarget 和撤单范围。用户明确批准这一准确摘要后，才可记录
一个不超过3分钟且不晚于当前授权截止时间的本地批准：

```bash
make paper-canary-approve \
  PROPOSAL_ID=paper-limit-proposal:<identity> \
  EXACT_LIMIT_PRICE=<用户看到并批准的准确两位小数> \
  APPROVED_AT=<带时区ISO时间> \
  EFFECTIVE_TO=<不晚于当前授权截止时间且不超过3分钟>
```

该命令仍不连接 MiniQMT。只有准确批准 ID 存在时，以下命令才可能调用一次
`order_stock`：

```bash
make paper-canary-submit APPROVAL_ID=paper-submission-approval:<identity>
```

提交入口在 Windows runner 内再次核对 simulation、准确账户、幂等备注、其他未完成
委托、可用现金和不超过3秒的卖一。卖一高于批准价格时禁止追价；任何超时或不确定结果
进入 `submission_unknown`，只能查询：

```bash
make paper-canary-status APPROVAL_ID=<identity> INTENT_ID=<可选>
make paper-canary-recover APPROVAL_ID=<identity> INTENT_ID=<可选>
```

不能用 `paper-canary-submit` 恢复未知状态。若准确金丝雀处于已确认或部分成交状态，
已批准范围内可且仅可撤销这一笔：

```bash
make paper-canary-cancel APPROVAL_ID=<identity> INTENT_ID=<可选>
```

15:00 后生成盘后收敛报告：

```bash
make paper-canary-converge APPROVAL_ID=<identity> INTENT_ID=<可选>
```

报告只有在本地投影、券商成交、现金、挂单和证券数量一致时才为 `converged`，并把
启动前数量保留为 `inherited`、本单确认增量记为 `managed`。阻断报告会冻结未来订单，
不得通过重跑提交命令绕过。

WP-0012 的以下命令只用于读取和复核历史 Local Replay，不再初始化正式前向环境，也
不重新查询券商：

```bash
make continuous-shadow-initialize \
  ACCOUNT_SNAPSHOT_ID=account-snapshot:<sha256> \
  RECONCILIATION_REPORT_ID=reconciliation-report:<sha256>
```

该命令按旧语义把模拟盘未归属资金/持仓分类为隔离外部状态，保留合成 50,000 元空仓
Local Replay 账本；兼容字段仍设置 `local_shadow_allowed=true`，始终输出
`broker_actions_allowed=false`。初始化后若没有准确晋级的 `PortfolioTarget`，状态
必须为 `waiting_for_promoted_portfolio_target`。

当前反转/量价 10 日版已经完成准确晋级，但生产数据截止 2026-07-24；在形成新鲜
`FeatureSnapshot → PredictionBatch → PortfolioTarget` 前，实际状态为
`waiting_for_fresh_feature_snapshot_and_portfolio_target`，不得用旧快照直接启动
当日 Shadow。

WP-0014 用准确的完成交易日日线推进已经启动的周期：

```bash
make continuous-shadow-advance \
  CYCLE_ARTIFACT=var/research/continuous-shadow/<identity>/cycle.json \
  SNAPSHOT_ID=snapshot:sha256:<包含观察日的准确快照> \
  THROUGH_DATE=YYYY-MM-DD
```

该命令不连接 MiniQMT。它在盘后以原始开盘价做延迟 Shadow 回放，逐日保存估值和
检查点，第 10 个观察交易日尝试退出；停牌或无可卖状态会顺延。`THROUGH_DATE` 早于
计划执行日时只返回 `waiting_next_open`，不生成未来成交。

## 战术研究管线烟测

下面的命令只证明生产快照到三类策略和统一回测引擎的技术贯通：

```bash
make tactical-research-smoke \
  SNAPSHOT_ID=snapshot:sha256:b0542da9ed6ea9d23f6827612002cbba19d2c99eb76224ebb2cf619e757dec2d \
  AS_OF=2026-07-24
```

结果写入 `var/research/`，明确标记为小样本管线证明，不得用作封存期结论或策略晋级。

## REQ-0005 事件回填与封存回放

WP-0008 的真实只读事件回填按交易日保存进度，可中断后重跑：

```bash
make tactical-event-backfill \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  BASE_SNAPSHOT_ID=snapshot:sha256:b0542da9ed6ea9d23f6827612002cbba19d2c99eb76224ebb2cf619e757dec2d
```

默认区间是 2023-01-01 至 2025-12-31。命令读取 `top_list`、`top_inst` 和
`stk_holdernumber`，不调用 MiniQMT，不读取账户；原始响应、分区进度和发布快照均在
Git 忽略的 `var/data/`。

事件快照完整发布后，显式运行九个冻结版本的全市场封存回放：

```bash
make tactical-sealed-replay SNAPSHOT_ID=<事件回填输出的 snapshot_id>
```

该命令固定开发截止 2022-12-31 和封存窗口 2023–2025，只读取快照清单中的精确
Parquet，结果写入 `var/research/sealed/`。两条命令都是长任务，不属于 `make check`；
生成证据不会自动晋级策略，也不会改变 `broker_enabled: false`。

扩展事件历史时显式指定区间；命令会把新分区与当前准确事件版本合并，不删除既有
2023–2026 观察：

```bash
make tactical-event-backfill \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  BASE_SNAPSHOT_ID=<当前准确快照> \
  START_DATE=2005-01-01 \
  END_DATE=2022-12-31
```

2000–2006 涨跌停只读覆盖核验使用：

```bash
make historical-price-limit-probe \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  BASE_SNAPSHOT_ID=<当前准确快照>
```

探测逐 SSE 开市日保存检查点和原始响应。输出 `backfill_ready` 只表示具备后续补齐
条件；命令本身固定 `publish_price_limit=false`，不会切换数据集或快照指针。任一空
响应输出 `historical_unavailable` 并继续保留 2007 年前未知缺口。

## REQ-0008 行业数据基础

WP-0009 的显式联网命令固化 SW2021 一级行业、当前与退出成员区间，以及 2000 年以来
提供方实际可得的行业指数日线：

```bash
make industry-data-foundation \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  BASE_SNAPSHOT_ID=<准确基础快照> \
  END_DATE=<基础快照市场截止日>
```

命令按行业和不超过五年的日期窗口保存进度，可在中断后重跑。它不调用 MiniQMT、
不读取账户、不计算生命周期或 ETF 信号；真实原始响应和发布物只进入 Git 忽略的
`var/data/`，不属于 `make check`。

## REQ-0002 正式行业相对轮动

WP-0010 只读取 WP-0009 的准确生产快照，生成内容寻址的正式轮动证据：

```bash
make market-rotation \
  SNAPSHOT_ID=snapshot:sha256:607680ae4f1a626ae9166696fa72ea03d70846273cd28cd9e3a852e2442a6af0
```

产物进入 `var/research/market-rotation/`，重复运行身份稳定。随后运行 `make dev`，
从首页可见入口进入 `/market?tab=industries&view=rotation`。API 为
`GET /api/market/industry-rotation`：没有当前快照返回 404，内容身份损坏返回 503，
不会回退到旧快照。该命令不联网、不接 MiniQMT、不读取账户，也不产生交易信号。

纯合成、无券商副作用的 Shadow 生命周期可单独运行：

```bash
make shadow-smoke
```

事件写入 Git 忽略的 `var/control/shadow.sqlite3`，使用 SQLite/WAL，重复事件幂等。
