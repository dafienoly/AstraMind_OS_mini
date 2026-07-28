# WP-0023A：持续 Paper 离线运行守护、备份恢复与故障演练

- 版本：1.0.0
- 状态：实现及本机离线部署验收完成
- 需求：REQ-2026-0009 v1.1.0、REQ-2026-0010 v1.2.0
- 阶段：4E、7
- UI 提案：不适用；不改变 WP-0020 已批准布局
- 日期：2026-07-28
- 券商授权：无；不连接 MiniQMT，不提交或撤销委托

## 目标

在首次真实 Paper 金丝雀之前，把已有不可变决策链、仓库外备份与恢复证据组织成一个
可重复、单实例、可从检查点恢复的离线守护，并用故障演练证明所有异常均失败关闭：

```text
备份/恢复
→ DataSnapshot
→ FeatureSnapshot
→ PredictionBatch
→ PortfolioTarget
→ OrderPlan
→ 风险与 Mandate 预览
→ Paper dispatch disabled
```

守护只核验已有身份链和本地运行前置，不联网更新数据、不重新计算策略，也不调用券商。

## 实现

- 新增独立 `local-ops.sqlite3` SQLite/WAL 控制台账，保存租约、任务检查点、守护结果和
  故障演练报告；它不是交易或研究真相源；
- 30秒租约通过 `BEGIN IMMEDIATE` 排除第二实例，过期租约可由新进程安全接管；
- 每一步完成后追加不可变检查点；进程中断后复用已完成步骤，不产生重复任务或副作用；
- 数据快照必须与决策链引用一致；缺失 Feature、Prediction、Target、OrderPlan 或
  Mandate 预览时，后续步骤跳过并给出恢复动作；
- 陈旧数据、外来挂单、Mandate 过期、`submission_unknown`、回调顺序异常或控制库
  不可写均阻断；
- 最后一步固定为 `paper_dispatch_state=disabled`，全部契约固定
  `broker_actions_allowed=false`；
- `make paper-offline-guard` 自动发现唯一持续 Shadow 产物、当前数据指针、本地授权、
  最新健康备份/恢复证据及已有 Paper 投影，不要求复制内部身份；
- `make paper-offline-fault-drill` 覆盖八类离线故障，报告明确记录 MiniQMT 连接和写入
  尝试均为零；
- 备份范围增加 `local_ops` 控制库，并将其列为未来 Paper 前置所需的 SQLite。

## 本机部署验收

私有 `.env.local` 已配置仓库外备份目录，实际目录不进入清单或日志。2026-07-28 完成：

- `pre_first_broker_write` 一致性备份：22个文件、4个 SQLite、无缺失源；
- 隔离恢复：22个文件哈希一致、4个 SQLite `integrity_check` 通过、Shadow 事件数为4；
- 八类故障演练全部通过；
- 离线守护八步全部完成，Paper dispatch 保持禁用；
- MiniQMT 连接尝试0次，券商写入尝试0次。
- `make check`：144个 Python 测试与6个 React 测试通过，耗时26.87秒；
- `make e2e-smoke`：4个浏览器流程通过。

实际身份：

- 备份：
  `local-backup:23e9fc3b61023a855e86adf48f9343e4654afd81504b29ce85fde3e2a3fd8d96`；
- 恢复：
  `recovery-drill:c1fe3d9e00af717778b85e7fa3dd4ad0cf0561bb738beb353bd387700cc1e4c3`；
- 故障演练：
  `offline-fault-drill:be2ae247fde8d0876d164238bfdc0de4d03725f051f9c6be47262ddb35a10a7c`；
- 守护：
  `offline-guard-run:1d187300f3fb664f8492e6049fb754345b06880f667dc0d2da7318e79b0be895`。

完整产物位于 Git 忽略的私有备份目录和 `var/`，仓库只记录脱敏身份与验收结果。

## 自动化证据

- 健康链路完成但 dispatch 永远禁用；
- 相同输入重复运行返回同一结果；
- 中断后从持久检查点恢复且任务不重复；
- 未过期租约阻断第二实例；
- 八类故障均进入准确阻断或只查询恢复；
- 备份篡改、SQLite 损坏和仓库内备份目录继续失败关闭。

直接证据：

- [离线守护与故障演练](../../../tests/unit/test_offline_paper_guard.py)
- [备份、恢复、篡改与保留](../../../tests/unit/test_local_operations.py)

## 非目标与后续

- 不连接 Tushare 或 MiniQMT，不运行真实数据更新；
- 不创建或激活持续 Paper StandingMandate；
- 不提交、重提、追价或撤销任何委托；
- 不替代 WP-0022 的窗口内准确文本确认；
- 不关闭 WP-0019/0021/0022 的真实券商验收；
- 下一步仍是 2026-07-29 金丝雀与盘后收敛；成功后再规划持续 Paper 的准确 Mandate
  和真实运行晋级。
