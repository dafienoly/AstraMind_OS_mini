# WP-0002A：双提供方能力探测与不可变快照框架

- 状态：已完成
- 需求：REQ-2026-0001 v1.0.1、REQ-2026-0004 v1.0.1
- 阶段：2A
- UI 提案：不适用
- 所有者：当前无首个提交的本地 `main` 工作区

## 目标

建立 Tushare/MiniQMT 只读能力矩阵、追加式原始证据、版本化数据集清单、
SQLite/WAL 控制台账和确定性 `DataSnapshot` 发布框架，为 WP-0002B 的首个生产数据
快照提供底座。

## 非目标

- 不进行历史回填，不发布生产 `DataSnapshot`，不建立持续实时流。
- 不读取账户、资金、持仓、委托或成交。
- 不导入交易模块，不下单、不撤单，不启用 Shadow、Paper 或 Live。
- 不实现产品 UI，不提交或推送 Git，不删除现有 `NUL` 文件。

## 允许文件

- Data 上下文的 contracts、application、ports 和 adapters；
- `scripts/provider_probe.py` 与只读 Windows runner；
- SQLite 追加式迁移、配置模板、Make 命令和依赖锁；
- 本工作包的测试、数据契约、计划、指南、决策和交接文档。

## 契约与数据影响

- 现有十个公共薄腰契约和 JSON Schema 保持兼容。
- Data 内部新增 `RawRecordEnvelope`、`DatasetManifest`、`ProviderCapability` 和
  `ProbeReport`。
- 原始记录、能力报告、内容寻址数据集和快照写入 Git 忽略的 `var/data/`。
- SQLite/WAL 只记录探测、数据集版本和快照身份；DuckDB 只能读取清单指定的
  版本化 Parquet。

## 授权与风险

用户已明确授权本工作包调用 Tushare 和 MiniQMT 行情/资料只读接口。Tushare 只读
加载旧 AstraMind `.env` 中的允许键；MiniQMT runner 只导入 `xtdata`，源码检查阻断
账户和交易接口。L2 默认不探测。

## 验收

1. Tushare 五项最小探测输出脱敏能力矩阵，权限或空数据不会伪装为成功。
2. MiniQMT 全量 Tick、K 线、交易日历、合约资料和有界订阅分别记录真实状态，
   任意失败不触及账户或交易。
3. 相同输入产生相同数据集/快照身份；同一不可变身份内容冲突时阻断。
4. SQLite 迁移可重复，DuckDB 拒绝未列入清单、通配或 `latest` 路径。
5. 默认 `make check` 不联网，显式 `make provider-probe` 才执行真实探测。

## 实际只读探测

- Tushare：`trade_cal`、`stock_basic`、`daily`、`adj_factor`、`daily_basic` 均返回
  可用小样本。
- MiniQMT：`get_full_tick`、交易日历和合约资料可用；闭市有界订阅没有收到新消息，
  正确记录为 `empty` 并退订；L2 为 `not_probed`。
- MiniQMT 小窗口 K 线探针因隔离 Windows Python 缺少 `numpy` 而记录为明确缺口，
  未临时修改外部 Python 环境。
- 探测没有读取账户、调用交易接口或留下订阅进程。

## 验收结果

- `make provider-probe`：Tushare 5/5 小样本可用；MiniQMT 3 项可用、K 线 1 项明确
  缺少 `numpy`、闭市订阅 1 项为空、L2 1 项未探测；命令正常退出。
- `make check`：14.55 秒，Python 16 项、Web 1 项及全部静态、架构、文档、密钥、
  规模和构建检查通过。
- 公共契约：既有 10 个 JSON Schema 无漂移。
- Git 忽略目录外不存在真实行情响应、Token、账户或订单数据。

## 下一安全动作

WP-0002B 使用本框架实现证券主表、交易日历、日线和复权因子的首个生产
`DataSnapshot`。MiniQMT 持续 L1 会话与不可变微批仍属于 WP-0002C。
