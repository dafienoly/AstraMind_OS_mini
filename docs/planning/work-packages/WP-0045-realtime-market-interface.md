# WP-0045：市场页盘中实时更新

- 状态：持续运营代码与 UI 已实现；Windows 任务曾安装，但 2026-07-30 审计发现
  行情会话当前运行失败、心跳陈旧，任务查询还可能把互操作失败误报为 `not_installed`；
  运行恢复、多周期分钟闭环和真实 15 分钟负载验收由 WP-0047 承接
- 需求：REQ-2026-0008 v1.11.0
- 阶段：6A、6B
- UI：UI-PROP-0001 v0.4（`approved`）
- 授权：MiniQMT 只读行情常驻、当前会话投影、市场页盘中临时层和验收

## 目标

让大盘与行业热力在保留最近完成日正式事实的同时，消费 MiniQMT 当前会话 SSE，
显示宽基指数、市场广度、成交额和行业热度的盘中临时变化，并明确市场时间、接收
时间、覆盖、`current`、`stale` 与 `disconnected`。

## 非目标

- 不把盘中临时值写回 `DataSnapshot`、生命周期或相对轮动快照；
- 不读取 MiniQMT 账户，不创建 `PortfolioTarget`、`OrderPlan` 或券商动作；
- 不新增独立实时页面，不改变五个一级入口；
- 不把休市无 Tick 自动解释为数据故障，状态必须结合交易会话表达。

## 运行规格

- Windows 任务名：`AstraMind OS Mini - Realtime Market`；
- 登录后和每日 08:55 启动，任务启动后持续运行；
- 仅在上海交易日 08:55–16:05 建立全推会话，闭市与休市保持进程等待；每个交易日
  和每次断线重连都生成新会话；
- 失败后按 Windows Task Scheduler 最小间隔 1 分钟重启，最多登记 999 次；禁止并发副本；
- WSL 进程锁提供第二层单实例保护；交易会话内至少每 5 秒、闭市等待时每 30 秒
  原子写入心跳，状态命令同时展示任务计划和进程新鲜度；
- 使用当前用户 `InteractiveToken` 与 `LeastPrivilege`；
- WSL 动作为仓库内 `make realtime-market-service-run`；
- `.env.local` 只在进程内读取，任务 XML 不写入 Token、账户或路径密钥；
- 暂停时终止当前进程并禁用任务；卸载时终止并删除任务。

## 页面规格

- 完成日标题、蜡烛、市场状态和生命周期结论保持正式日度身份；
- 一条“盘中会话脉冲带”显示状态、市场时间、接收时间、1 秒粒度与覆盖；
- 大盘将当前指数、上涨/下跌家数和成交额作为盘中临时覆盖层展示；
- 行业热力可切换/叠加盘中行业热度，但不改写正式日度行业排序；
- SSE 中断时保留最后完成日内容，盘中区域显示 `disconnected`；
- 十秒无有效更新显示 `stale`，未知状态不使用绿色。

## 允许文件

- `src/astramind_mini/local_ops/realtime_service_deployment.py`
- `scripts/manage_realtime_market_service.py`
- `scripts/manage_realtime_market_service_elevated.ps1`
- `scripts/run_miniqmt_realtime_pipeline.py`
- `scripts/dev.py`
- `src/astramind_mini/data/realtime_api.py`
- `Makefile`
- `apps/web/src/market-dashboard/**`
- `tests/unit/test_realtime_service_deployment.py`
- `tests/unit/test_realtime_projection.py`
- `tests/integration/test_realtime_market_api.py`
- 对应前端测试和 `tests/e2e/foundation.spec.ts`
- UI-PROP-0001 v0.4、需求、计划、运行指南和追踪索引

## 验收

1. Windows 登录或任务失败后，实时管线自动恢复且不启动第二实例；
2. SSE 使用一个当前会话身份，并传递市场时间、接收时间、覆盖和状态；
3. 页面首次通过 GET 建立基线，再由 `EventSource` 连续更新；
4. `current`、`stale`、`disconnected` 与完成日正式事实视觉和语义分离；
5. 页面卸载时关闭 `EventSource`，重连不制造重复订阅；
6. 连续 15 分钟全市场负载无未解释断线、队列溢出或聚合身份冲突；
7. 从 `latest_received_at` 到浏览器渲染的端到端 P95 不超过 2 秒；
8. 桌面、窄屏、刷新恢复、断线降级和真实截图通过；
9. 所有输出保持 `broker_actions_allowed=false`。
10. 一秒市场/行业结果只更新当前投影，不长期保存；一分钟 K 线长期保存，最后一个
    未闭合分钟在会话结束时冲刷；原始与规范化细粒度负载只保留五个交易日。
11. SSE 轮询不得在 API 事件循环内同步解压和解析全市场投影；未变化的投影按文件
    修订复用解析结果。开发服务热重载时最多等待三秒关闭仍在线的 SSE，随后取消旧
    worker 的连接并完成进程换代，不能让轮动、ETF 或个股页面拖死全部查询接口。

## 2026-07-29 稳定性修复记录

- 故障表现：轮动页停留在“正在加载正式轮动快照”，同时 `/openapi.json` 等无关
  API 也超时；
- 根因：多个 SSE 每 250 ms 同步解压并解析全市场证券投影，且开发热重载无限等待
  浏览器长连接退出，造成事件循环饥饿和新旧 worker 重叠；
- 修复：投影读取增加文件修订缓存，磁盘读取与 Pydantic 解析移出事件循环，轮询
  调整为 1 秒；流主动检测客户端断开，开发 worker 优雅退出上限为 3 秒；
- 证据：两个证券 SSE 持续连接时触发代码热重载，旧 worker 到期取消连接并成功
  换代；换代后行业轮动 API 返回 200，正式轮动浏览器流程完整通过。

## 保护边界

本包只授权只读行情和页面观察，不授权 MiniQMT 账户、Paper、Live、委托、撤单或
任何资本动作。
