# WP-0031：本地日度调度、错过窗口补跑与启动恢复

- 版本：1.1.0
- 状态：已完成
- 需求：REQ-2026-0009 v1.2.0
- 上游：WP-0030 v1.1.0
- 阶段：7
- UI 提案：后端与本机部署，不适用
- 日期：2026-07-28
- 目标包：Daily Ops 1.0，第二里程碑
- 批准：用户于 2026-07-29 批准实施并要求完成实际安装；安装前精确预览门保留
- 券商授权：无；调度器不得连接交易网关

## 目标

让 WP-0030 的统一入口在本地按日可靠启动，并在电脑关机、WSL 未运行、提供方延迟或
进程中断后安全补跑，不要求 API 或浏览器常驻。

## 调度口径

- 16:35 首次运行，提供方未完成时在 16:50、17:10 有界补跑；
- 次日 08:30 只做启动恢复和上一交易日完成度核验；
- 交易日来自版本化日历，不按自然日猜测；
- 同一目标日期始终复用 WP-0030 幂等身份；
- 超过 REQ-2026-0009 的 30 分钟预算后停止自动重试并进入异常收件箱；
- 电脑错过全部窗口后，下一次启动只补最近一个未完成交易日，不自动展开长历史回填。

## 范围

- 建立与平台无关的调度决策器和确定性合成时钟测试；
- 生成 Windows Task Scheduler 可审查任务定义和 WSL 安全启动包装器；
- 提供预览、安装、状态、暂停和可恢复卸载命令；
- 安装前显示准确命令、触发时间、工作目录和环境文件来源；
- 任务只调用 `make daily-run`，不持有 Token、不复制 `.env.local`；
- 记录错过窗口、补跑、租约冲突、超时和最近成功日期；
- 启动恢复不得执行 Paper 查询、提交、撤单或 Live。

## 非目标

- 不建立常驻云服务、容器集群或企业调度平台；
- 不让浏览器、FastAPI 请求或页面刷新直接联网补数；
- 不把系统计划任务定义当作研究或数据身份；
- 不自动安装任务；实际安装属于本机状态变更，实施验收前再次向用户展示并确认；
- 不执行真实交易日等待测试，使用合成时钟和显式本地试跑验收。

## 允许修改

- `src/astramind_mini/local_ops/` 的调度判断与部署状态；
- `scripts/` 的 Windows/WSL 调度包装器；
- `Makefile`；
- `docs/development/` 的安装、暂停、恢复和卸载指南；
- 聚焦测试。

## 受保护动作

- 生成和测试任务定义不需要券商授权；
- 执行实际 `schedule-install` 前必须获得用户对任务名称、触发时间和工作目录的确认；
- 调度器永久排除 `paper-canary-run`、`paper-canary-settle`、MiniQMT 和 Live 命令。

## 验收

1. Given 正常交易日，When 合成时钟到达三个盘后触发点，Then 同一目标日期最多形成一个
   活跃运行身份，后续触发只恢复或读取结果。
2. Given 首次运行得到 `waiting_provider`，When 到达补跑时间，Then 从安全检查点继续，
   不重复已保存原始响应。
3. Given 电脑错过盘后窗口，When 次日启动，Then 只补最近一个未完成交易日并显示原因。
4. Given 任务已运行或租约仍有效，When 第二个触发器启动，Then 第二实例退出且不破坏
   第一实例。
5. Given 用户预览安装，When 检查任务定义，Then 不含 Token、账户标识、Windows 用户
   私有路径或任何 Paper/Live 命令。
6. Given 暂停或卸载调度，When 查看本地数据和历史，Then 已发布快照、运行摘要和控制
   台账不被删除。

## 检查

```text
uv run pytest tests/unit/test_daily_scheduler.py
uv run pytest tests/integration/test_daily_scheduler_wrapper.py
make docs-check
make check
git diff --check
```

## 实施证据

- 平台无关决策器覆盖 08:30、16:35、16:50、17:10、登录恢复和版本化交易日历；
- Windows 任务定义使用 least privilege、`StartWhenAvailable`、35 分钟上限和
  `IgnoreNew`，动作只进入 `make daily-schedule-trigger`；
- 预览已于 2026-07-29 生成，任务名称为
  `AstraMind OS Mini - Daily Ops`，工作目录为
  `/home/ly/work/AstraMind_OS_mini`，环境来源为
  `/mnt/e/work/AstraMind_OS/.env`；
- 用户于 2026-07-29 精确确认后完成 Windows Task Scheduler 实际安装；内置 Users 组
  任务通过 UAC 登记，任务本身保持 `LeastPrivilege`；
- `make daily-schedule-status` 确认 `state=installed`，Windows 状态为 `Ready`，共五个
  触发器，首次计划运行是 2026-07-29 16:35；
- 单元与包装器集成测试验证同一运行身份、提供方有界重试、错过窗口恢复、XML 敏感信息
  排除和零券商动作。

## 交接

- 下一工作包：WP-0032；
- 无实际系统任务安装时，可以完成代码与合成验收，但部署状态必须显示“未安装”；
- 实际安装、暂停或卸载结果必须在本机运行指南中留下脱敏证据。
