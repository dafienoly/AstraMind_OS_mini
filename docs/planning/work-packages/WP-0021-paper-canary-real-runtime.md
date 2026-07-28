# WP-0021：Paper 金丝雀真实预检、一次性提交与盘后收敛

- 版本：1.0.0
- 状态：实现完成；真实券商写入仍等待窗口内确切数值批准
- 需求：REQ-2026-0010 v1.2.0、REQ-2026-0006 v1.4.0
- 阶段：4E
- UI 提案：沿用已批准 UI-PROP-0003/0006/0007/0008 v0.1；不改变布局
- 日期：2026-07-28

## 目标与非目标

把 WP-0018/0019 已有授权骨架、状态机和 MiniQMT 网关接成一个失败关闭的真实 Paper
金丝雀运行闭环：

`新鲜账户证据 → 新鲜卖一 → 确切批准 → 真实预检 → 唯一提交 → 查询/限定撤单 →
盘后收敛`。

本工作包实现命令和自动化证据，不代替用户在 2026-07-29 09:35～09:45 对准确数值
摘要和首次 `order_stock` 的最终批准。本次实施未连接 MiniQMT，未创建
`PaperSubmissionApproval`，未提交或撤销委托，也未启用 Live。

## 实现

- 将 `PaperPreflightDecision` 区分为合成离线证据和 `real_miniqmt` 证据；真实预检
  逐项绑定授权、提案、批准、模式锁、账户基线和账户快照；
- 买入预检检查 simulation 模式、无外来挂单、账户/提案基线一致、现金及费用缓冲、
  100股整手、窗口、3秒行情、证券资料、风险警示、上市初期、10%涨停边界、8%回撤
  禁止扩大风险和准确 Mandate；
- PAPER `OrderPlan` 身份由 PortfolioTarget、StandingMandate、授权和最终批准确定；
  重启或重复预检不产生第二个订单计划或幂等键；
- `paper-canary-approve` 只保存不超过3分钟、且不越过09:45的准确数值批准，不连接
  MiniQMT；
- `paper-canary-submit` 要求准确批准 ID，在 Windows runner 内再次查询幂等备注、
  阻断其他未完成委托、重查可用现金和3秒卖一，只允许同步普通股票限价提交一次；
- 超时或网关异常一律记录为 `submission_unknown`，后续只能运行查询恢复；状态命令
  不提供自动重提；
- 撤单命令重新验证完整金丝雀血缘，只允许已经确认或部分成交的这一笔；
- 盘后命令重新查询订单并建立新完整账户快照，以券商订单指纹核对成交，区分
  `inherited` 与 `managed` 数量，并校验现金、持仓、挂单和本地投影；任何差异冻结
  后续订单；
- 追加迁移 `0010` 保存真实预检与盘后收敛报告；操作投影可显示提案、批准、工作中、
  未知恢复和终态，不新增提交按钮。

## 命令边界

```text
paper-canary-stage-limit   连接只读账户和行情；不写券商
paper-canary-approve       只写本地准确批准；不写券商
paper-canary-submit        唯一可能调用一次 order_stock 的显式命令
paper-canary-status        只查询券商事实
paper-canary-recover       仅 submission_unknown 查询恢复
paper-canary-cancel        仅撤销本次金丝雀
paper-canary-converge      15:00 后只读查询并生成收敛报告
```

这些命令不加入 `make check`，也不由页面、启动过程或定时任务自动调用。提交命令缺少
准确批准、时间越界、卖一上涨、行情陈旧、现金不足、回撤达到8%、证券不可交易或存在
外来挂单时均在券商写入前失败关闭。

## 自动化证据

- 真实预检证据绑定、现金/回撤/证券状态负例；
- 最终批准价格完全匹配、短有效期和窗口边界；
- PAPER OrderPlan 重启身份稳定；
- Windows runner 在委托前重查幂等、挂单、现金和实时卖一；
- 网关异常进入 unknown，禁止重提；
- 盘后 inherited/managed、成交、现金和挂单收敛；
- SQLite/WAL 追加式迁移、操作投影和脱敏 API。

直接证据：

- [真实预检与收敛](../../../tests/unit/test_paper_canary_runtime.py)
- [持续网关与幂等](../../../tests/unit/test_miniqmt_paper_gateway.py)
- [状态机与未知恢复](../../../tests/unit/test_paper_execution_offline.py)
- [操作投影 API](../../../tests/integration/test_paper_operations_api.py)

## 剩余受保护验收

真实运行仍严格分两步：

1. 窗口内运行只读基线和行情提案，把证券、方向、数量、确切限价、金额、行情时间、
   账户/授权/目标身份和撤单范围展示给用户；
2. 用户明确批准该准确摘要后才发布 `PaperSubmissionApproval` 并运行唯一提交命令。

窗口结束、用户没有确认或任何预检失败时，当日安全结束。真实确认/成交/唯一撤单和
盘后报告完成后，WP-0019 的券商运行验收才可关闭；WP-0021 的开发实现本身已完成。
