# 本地开发指南

- 适用工作包：WP-0001、WP-0002A、WP-0002B
- 当前状态：阶段 1A/1B、2A 和 2B 历史行情快照已建立，阶段 1C/1D 未开始

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

WP-0002C 已获授权调用 MiniQMT 行情 RPC，但账户和交易仍未授权：

```bash
make miniqmt-l1-capture CAPTURE_SECONDS=5
```

命令只调用 `xtdata.subscribe_whole_quote` 与退订接口，原始和规范化 gzip 微批写入
Git 忽略的 `var/data/realtime/miniqmt/`。超时或异常会终止 runner；输出不打印真实
行情值。首次真实验收使用 `xtquant_250516`，完成 SH/SZ/BJ 全推与退订。

UI Lab 位于 `http://127.0.0.1:5174/dev/ui-lab`。它只使用合成 Fixture，不读取
实时行情或账户。

## 战术研究管线烟测

下面的命令只证明生产快照到三类策略和统一回测引擎的技术贯通：

```bash
make tactical-research-smoke \
  SNAPSHOT_ID=snapshot:sha256:b0542da9ed6ea9d23f6827612002cbba19d2c99eb76224ebb2cf619e757dec2d \
  AS_OF=2026-07-24
```

结果写入 `var/research/`，明确标记为小样本管线证明，不得用作封存期结论或策略晋级。

纯合成、无券商副作用的 Shadow 生命周期可单独运行：

```bash
make shadow-smoke
```

事件写入 Git 忽略的 `var/control/shadow.sqlite3`，使用 SQLite/WAL，重复事件幂等。
