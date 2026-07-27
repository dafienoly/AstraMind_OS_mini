---
status: accepted
---

# ADR-0001：采用本地优先的模块化单体

AstraMind OS Mini 采用 FastAPI/React 模块化单体，通过明确的上下文端口隔离功能；研究数据使用 Parquet/DuckDB，小型事务控制状态使用 SQLite/WAL。

这样可以让个人系统容易理解、安装和运行，同时允许独立替换数据、模型、优化器和券商适配器。被否决的方案是把旧 AstraMind 的服务拆分、发布状态、身份认证和任务治理复杂度整体搬入新项目。
