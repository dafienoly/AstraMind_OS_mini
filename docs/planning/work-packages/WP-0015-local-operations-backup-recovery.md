# WP-0015：本地日常调度、备份与恢复基线

- 版本：1.0.0
- 状态：实现完成；真实外部备份与首次恢复演练已由 WP-0023A 完成
- 需求：REQ-2026-0009 v1.1.0
- 阶段：7；同时是未来 Paper 的安全前置
- UI 提案：不适用；UI-PROP-0008 v0.1 已批准并由 WP-0020 实现
- 券商授权：无；不连接 MiniQMT，`broker_actions_allowed=false`
- 日期：2026-07-28

## 目标

用少量显式本地命令固化日度运行窗口、仓库外一致性备份、30 日/12 月保留和隔离恢复
演练，不引入常驻调度平台，也不让备份就绪状态推导出 Paper 授权。

## 实现

- `ops-plan` 按 `Asia/Shanghai` 评估 16:30～17:00 盘后窗口和次交易日
  08:30～09:20 盘前恢复窗口；
- 提供方未确认完成时阻断盘后流水线；超过 30 分钟且未完成时进入 `stale`；
- 盘前备份或恢复未就绪时明确阻断未来 Paper 预检；
- `ops-backup` 使用 SQLite Backup API 一致性复制控制、Shadow 和研究晋级数据库，
  同时保存当前数据版本指针；
- 备份目录必须由 `ASTRAMIND_BACKUP_DIR` 指向仓库和 `var/` 之外；清单只记录逻辑名、
  相对路径、大小和哈希，不记录绝对路径、Token 或账户标识；
- 保留最近 30 个日度恢复点，并保留最近 12 个自然月各自最后一个恢复点；
- `ops-recovery-drill` 只恢复到 Git 忽略的隔离目录，核对文件哈希、SQLite
  `integrity_check` 和 Shadow 事件数量，不覆盖当前运行状态；
- 缺少外部目录、备份不完整、文件篡改或 SQLite 损坏均返回非零和可执行恢复提示。

## 命令

```bash
make ops-plan \
  TRADING_DATE=YYYY-MM-DD \
  NEXT_TRADING_DATE=YYYY-MM-DD \
  OPS_AT=带时区的ISO时间 \
  PROVIDER_COMPLETE=true

make ops-backup BACKUP_REASON=daily_close LOGICAL_DATE=YYYY-MM-DD

make ops-recovery-drill BACKUP_ID=local-backup:<identity>
```

`ops-backup` 与 `ops-recovery-drill` 要求在本机秘密配置中设置
`ASTRAMIND_BACKUP_DIR`。本工作包没有猜测或写入实际路径；未配置时正确返回
`backup_directory_not_configured`，研究与 Shadow 不因此停用，但
`paper_backup_ready=false`。

## 验收证据

- 窗口测试覆盖提供方未完成、30 分钟超时、盘前恢复阻断和永久券商禁用；
- SQLite/WAL 源库、数据指针和配置指纹形成确定性、幂等、无绝对路径的备份；
- 隔离恢复证明两个 SQLite 完整、Shadow 事件计数一致，重复演练身份稳定；
- 篡改备份生成 `blocked` 报告，不能成为 Paper 前置证据；
- 保留选择证明最近 30 日和最近 12 个月月末恢复点不会被清理；
- 实际 `ops-plan` 验收得到 `post_close/ready`，备份和恢复命令在未配置目录时安全阻断。

## 非目标与后续

- 不执行真实盘后数据更新或自动守护；作业仍由显式命令触发；
- 不备份真实 Token、账户 ID 或 Windows userdata 路径；
- 不实现 UI-PROP-0008；
- 不替代不可变 Parquet 数据的内容寻址存储，也不建立第二数据真相；
- 首次真实外部备份和恢复演练已由 WP-0023A 使用私有配置完成；
- 本工作包不授权 MiniQMT 连接、Paper 下单、撤单、常设授权或 Live。
