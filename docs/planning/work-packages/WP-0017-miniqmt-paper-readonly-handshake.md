# WP-0017：模拟盘模式锁、完整账户基线与只读回调握手

- 版本：1.0.0
- 状态：实现完成并通过真实模拟盘只读验收
- 需求：REQ-2026-0010 v1.0.0
- 阶段：4E
- UI 提案：不适用；UI-PROP-0003/0006/0007/0008 v0.1 仍待批准
- 券商授权：仅一个准确模拟盘账户的只读连接、完整查询和回调订阅生命周期
- 日期：2026-07-28

## 目标

在不产生券商写入的前提下，建立一个短时持久 MiniQMT 会话，以模式锁核对准确模拟盘
账户，读取资金、持仓、委托和成交完整基线，并完成
`register_callback → subscribe → observe → unsubscribe → stop` 生命周期。

## 实现

- 命令启动前要求私有配置明确为 `simulation`；`live`、缺失或未知模式不会启动 runner；
- Windows runner 通过 `query_account_infos` 和 `query_account_status` 精确匹配配置的唯一
  账号，核对股票账户类型和就绪状态，不输出或保存原始账号；
- 同一只读会话查询资金、全部持仓、当日委托和当日成交，发布新的不可变
  `AccountSnapshot`；
- 回调只收集账户状态、资产、持仓、委托、成交及断线类型和计数，不保存回调原始值；
- 闭市或观察窗口没有主推时记录 `quiet`，不伪造回调；订阅、退订、目标账号或连接任一
  不确定时失败关闭；
- `PaperAccountBaseline` 将所有既有持仓标记为 `inherited`，`managed` 数量固定为零，
  既有挂单单独列为阻断；
- 模式锁、回调握手和账户基线通过追加迁移 `0007_paper_readonly_startup.sql` 保存；
- runner 源码不包含任何委托或撤单调用，发布结果始终
  `broker_actions_allowed=false`、`new_orders_frozen=true`。

## 模式证据边界

本机 `xtquant_250516` 的 `query_account_infos()` 实际未返回官方文档列出的
`account_classification` 值。因此系统没有猜测其数值，而是记录
`account_classification_not_returned` 缺口。

有效模式锁由四项联合事实组成：私有配置选择 `simulation`、券商返回中只有一个精确
账号匹配、账户类型为股票、账户状态正常或收盘。该锁只证明本次获准只读会话准确命中
已配置模拟盘，不授权任何写入；若未来客户端返回账户分类，则作为附加证据记录。

## 命令

```bash
make miniqmt-paper-readonly-handshake
```

命令只输出脱敏身份、计数、状态和阻断码。完整证据保存于 Git 忽略的
`var/control/`。

## 真实验收

- 客户端：`xtquant_250516`；
- 模式锁：
  `broker-account-mode-lock:6ddd5e099112ff57e7dfc87b5a0708b9a641bbfe26fe2305816589148b6c139a`；
- 账户快照：
  `account-snapshot:21b9b719490a180bd80fd2beb4fadb99a87613185580f233cbd387eb988f8a34`；
- 回调握手：
  `readonly-callback-handshake:879183b11192b895f63c0f37ea3078104a115ffa8f9090998514ef496a2bf463`；
- Paper 基线：
  `paper-account-baseline:a96048cdf9506f11075144a06159a73cd167b9f6b262709eed49b58ffcd443a8`；
- 完整基线含 1 个既有持仓、0 个未完成委托；两秒窗口无账户变化，回调状态为
  `quiet`，订阅与退订均成功；
- 启动状态保持 `blocked`，阻断码为 `paper_write_not_authorized` 和
  `standing_mandate_missing`；
- runner 完成后没有遗留 Windows 子进程或临时目录，没有券商写入。

## 验收证据与下一步

合成测试覆盖 Live 预启动拒绝、账号不匹配、状态异常、分类缺口、外来回调、退订失败、
闭市静默、完整基线、追加存储、重启读取及 runner 清理。直接证据见
[test_paper_readonly_startup.py](../../../tests/unit/test_paper_readonly_startup.py)。

WP-0017 可以关闭。下一项 WP-0018 涉及第一份准确 `StandingMandate` 和模拟盘金丝雀
写入，必须由用户另行明确批准授权范围、证券、金额、时段、有效期及首笔委托；当前
工作包不提供可调用的写入路径。
