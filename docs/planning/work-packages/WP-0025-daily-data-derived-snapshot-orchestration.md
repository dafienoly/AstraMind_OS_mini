# WP-0025：日度数据增量与派生快照编排

- 版本：1.0.0
- 状态：规划完成，未授权实施或联网运行
- 需求：REQ-2026-0009 v1.1.0、REQ-2026-0002 v1.2.0、REQ-2026-0008 v1.1.0
- 阶段：2、6C、7
- UI 提案：后端不适用；轮动页状态使用已批准的 `UI-PROP-0002 v0.2`
- 日期：2026-07-28
- 券商授权：无；不连接账户或交易接口

## 目标

在交易日收盘且提供方确认数据完整后，用一个可恢复的本地日度作业依次更新交易日历、
申万行业日线、生产 `DataSnapshot` 和 `MarketRotationSnapshot`，原子发布最新指针，
并让 API 与界面能够区分当前、陈旧、阻断和恢复中状态。

## 原则

```text
本地调度
→ 提供方完成度探测
→ 原始记录只追加
→ 版本化标准数据集
→ 不可变 DataSnapshot
→ MarketRotationSnapshot
→ 原子切换 current
→ API/界面只读消费
```

- 一个调度作业更新唯一数据管线；页面或功能模块不得各自拉取提供方数据；
- “最新”只是一枚经过完整发布后更新的指针，不进入研究身份；
- 任何步骤失败都保留上一个完整版本，并把新鲜度标记为 `stale` 或 `blocked`；
- 不把长历史回填、完整回测或模型训练塞入日度关键路径。

## 范围

- 复用 REQ-2026-0009 已批准的 `Asia/Shanghai` 和 16:30 后盘后窗口；
- 从版本化交易日历推导最近完成交易日，同时核验提供方已发布该日数据；
- 增量更新 `trade_calendar`、`industry_index_daily` 及其原始响应；
- 只在所有 31 个 `SW2021:L1` 行业满足覆盖规则时发布行业数据版本；
- 构建包含准确数据集版本的生产 `DataSnapshot`；
- 基于该快照重算最近 60 个输出交易日的 `MarketRotationSnapshot`；
- 使用临时文件、同步落盘和原子替换更新各 `current` 指针；
- 记录作业身份、输入、步骤、尝试次数、耗时、结果和脱敏错误；
- 支持相同幂等键恢复，不重复发布或制造内容冲突；
- 提供显式命令用于手动运行、查看状态和从安全检查点恢复；
- 可选接入本地 OS 计划任务；不要求 API 服务常驻才能更新数据。

## 非目标

- 不由浏览器页面加载触发 Tushare 或 MiniQMT；
- 不常驻订阅 MiniQMT 行情，不读取账户、持仓、委托或成交；
- 不更新策略、组合、OrderPlan、Shadow 或 Paper；
- 不静默以 MiniQMT 替代 Tushare，或以旧快照伪装当前数据；
- 不把全历史回填和修复塞进单次日度运行；
- 不建立第二套任务系统或企业调度平台。

## 允许修改

- `src/astramind_mini/data/application/` 的日度增量服务
- `src/astramind_mini/data/ports/`
- `src/astramind_mini/data/adapters/` 的只读提供方与发布适配器
- `src/astramind_mini/market_regime/` 的轮动构建调用
- `src/astramind_mini/local_ops/` 的通用租约与作业状态复用点
- 新的追加式 SQLite 迁移
- `scripts/` 中单一编排入口
- `Makefile` 中显式本地命令
- 聚焦测试和直接文档

## 高争用文件

- `Makefile`
- `src/astramind_mini/composition.py`
- Data SQLite 迁移目录
- `docs/data/data-contracts.md`
- `docs/planning/phased-implementation-plan.md`

## 数据与点时边界

- 交易日不是“今天日期”；必须是交易日历和提供方完成状态共同确认的最近完成交易日；
- 原始响应保留提供方、请求身份、接收时间和内容哈希，只追加不覆盖；
- 标准数据集只能追加新版本，历史更正产生新版本和缺口说明；
- 同一次编排固定一个源版本集合，不混用不同运行中途出现的“最新”；
- `DataSnapshot.as_of` 不得早于所引用数据的可用时间，也不得晚于实际完成证据；
- 轮动快照只接受内容校验通过的准确 `DataSnapshot`；
- 页面新鲜度由“预期完成交易日”和“快照最后交易日”比较得出。

## 运行状态

- `waiting_window`：尚未到盘后窗口；
- `waiting_provider`：交易日已结束，提供方尚未完整；
- `running`：持有单实例租约并执行有界步骤；
- `current`：全部指针与最近完成交易日一致；
- `stale`：仍可读取旧快照，但落后于预期日期；
- `blocked`：关键覆盖、身份冲突、损坏或重试预算耗尽；
- `recovery_required`：存在可恢复检查点，需要显式继续；
- `no_session`：非交易日且当前快照仍符合最近完成交易日。

## 验收

1. Given 提供方尚未发布完整当日行业数据，When 16:30 后运行，Then 状态为
   `waiting_provider` 或 `stale`，当前指针不变。
2. Given 31 个行业当日数据完整，When 运行编排，Then 按顺序发布数据集、
   `DataSnapshot` 和轮动快照，最后一次性切换当前指针。
3. Given 在任一步骤被中断，When 使用同一幂等键恢复，Then 已完成内容不重复，未完成
   步骤继续，且没有半发布指针。
4. Given 同一输入重复运行，When 比较产物，Then 内容身份一致且不会制造第二份逻辑
   版本。
5. Given 一个行业缺失或内容身份冲突，When 尝试发布，Then 作业进入 `blocked` 并保留
   最后完整快照。
6. Given 页面或 API 启动，When 数据已经落后，Then 只读取数据管线状态并显示恢复动作，
   不从请求处理路径联网补数。
7. Given 日度任务运行，When 扫描日志和状态证据，Then 不包含 Token、Windows 用户
   路径、真实行情值、账户标识或订单载荷。

## 检查

```text
uv run pytest tests/unit/test_daily_data_orchestration.py
uv run pytest tests/integration/test_rotation_api.py
make docs-check
make secrets-check
git diff --check
```

真实提供方验收是显式联网命令，不加入 `make check`。

## 交接

- 实施前应确认当日提供方完成判定和任务实际开始时间；
- 后端可以独立于 UI 实施；轮动页变化只能按已批准的 `UI-PROP-0002 v0.2` 进行；
- 本工作包完成也不授权券商连接、策略推进或 Paper/Live；
- 下一安全动作：批准实施后，先用合成两交易日和中断恢复 Fixture 建立编排核心。
