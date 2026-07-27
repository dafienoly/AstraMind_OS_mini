---
status: accepted
---

# ADR-0004：MiniQMT 行情与交易使用独立端口

东莞证券 MiniQMT 的本地 RPC 同时提供行情、资料、账户和交易能力。AstraMind OS Mini
可以复用一个隔离的本机桥接进程，但 Data 与 Trading Execution 必须分别通过行情端口
和交易端口访问，拥有独立配置、健康状态、权限和测试替身。

行情原始记录进入 Data 的版本化快照体系；账户查询、委托、撤单和回调进入 Trading
Execution 的账户快照与 `ExecutionEvent` 体系。MiniQMT SDK、RPC 客户端、缓存和账户
状态都不能进入领域契约，也不能成为第二套策略、组合或执行真相。

这样既能充分复用实时 L1、历史资料和模拟/实盘能力，又不会让一个供应商适配器绕过
`DataSnapshot → PortfolioTarget → OrderPlan` 的产品边界。
