# 本地开发指南

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

诊断页只证明 FastAPI、React/Vite 和浏览器链路可用，不代表产品 UI 已实现。

## 稳定检查

- `make doctor`：必需工具或端口失败时返回非零；CLI 与 GPU 缺失只警告。
- `make check`：格式、lint、类型、单元、契约、架构、文档、密钥、规模和构建。
- `make docs-check`：只运行本地链接、SVG、批准记录、密钥和规模等仓库文档检查。
- `make e2e-smoke`：临时启动本地服务，运行可见浏览器流程并清理子进程。
- `make contracts-generate`：公共契约变更后重新生成 JSON Schema。
- `make contracts-check`：验证生成 Schema 与 Pydantic 模型没有漂移。

历史重建、模型训练、Shadow 和券商探查都不属于这些默认命令。

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

WP-0012 使用 WP-0011 已保存的准确证据身份初始化纯本地持续 Shadow，不重新查询
券商：

```bash
make continuous-shadow-initialize \
  ACCOUNT_SNAPSHOT_ID=account-snapshot:<sha256> \
  RECONCILIATION_REPORT_ID=reconciliation-report:<sha256>
```

该命令把模拟盘未归属资金/持仓分类为隔离外部状态，保留合成 50,000 元空仓 Shadow
账本；只设置 `local_shadow_allowed=true`，始终输出
`broker_actions_allowed=false`。初始化后若没有准确晋级的 `PortfolioTarget`，状态
必须为 `waiting_for_promoted_portfolio_target`。

当前反转/量价 10 日版已经完成准确晋级，但生产数据截止 2026-07-24；在形成新鲜
`FeatureSnapshot → PredictionBatch → PortfolioTarget` 前，实际状态为
`waiting_for_fresh_feature_snapshot_and_portfolio_target`，不得用旧快照直接启动
当日 Shadow。

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
