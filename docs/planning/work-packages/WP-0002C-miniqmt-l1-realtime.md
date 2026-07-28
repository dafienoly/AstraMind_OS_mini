# WP-0002C：MiniQMT L1 全推与不可变实时微批

- 状态：已完成
- 需求：REQ-2026-0004 v1.0.1
- 完成日期：2026-07-27
- 授权：仅 MiniQMT 本地行情 RPC；不含账户、委托、撤单、Paper 或 Live
- UI：不适用

## 目标与非目标

目标是建立 SH/SZ/BJ L1 全推的有界会话、显式订阅/退订、重复观察消除，以及原始
与规范化内容分离的不可变 gzip 微批。L2、历史快照选源、券商账户和交易动作均不在
本工作包内。

## 实现与证据

- Windows runner 只导入 `xtquant.xtdata`，调用 `subscribe_whole_quote` 与
  `unsubscribe_quote`；
- WSL 适配器对 runner 设置超时，超时会终止 Windows 子进程；
- `RealtimeQuoteObservation`、`QuoteMicroBatch` 和 `FeedSessionReport` 均为严格、
  冻结、禁止额外字段的 Data 内部契约；
- 原始全推与规范化观察分别写入 `var/data/realtime/miniqmt/sessions/`，相同路径内容
  冲突会阻断；
- `make miniqmt-l1-capture CAPTURE_SECONDS=1` 完成真实验收：
  `xtquant_250516`、2 个全推消息、26,768 条规范化观察、退订成功；
- 失败 runner 最多执行两次有界重连，测试覆盖一次断线后恢复；接收时间可按阈值判定
  陈旧；
- 会话证据身份：
  `sha256:c8963a0c964946e8a635332030f96d194ae72f7d56d33f7df1e93dea8f0e5695`。

## 验收与边界

单元测试覆盖去重、规范化、不可变冲突、断线重连、陈旧判断和 runner 源码禁用交易
表面。本次真实会话未发生断线，因此记录 `disconnects=0`，没有伪造真实重连事件。
持续守护和跨会话新鲜度告警属于后续运行工作包。未读取或保存任何账户信息。
