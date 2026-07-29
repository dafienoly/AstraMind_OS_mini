# WP-0030：统一日常运行编排与不可变运行摘要

- 版本：1.2.0
- 状态：已完成
- 需求：REQ-2026-0009 v1.2.0、REQ-2026-0005 v1.1.0、REQ-2026-0006 v1.4.0
- 上游：WP-0025 v1.2.0、WP-0029 v1.0.0
- 阶段：7
- UI 提案：后端与命令行，不适用
- 日期：2026-07-28
- 目标包：Daily Ops 1.0，第一里程碑
- 批准：用户于 2026-07-28 批准八小时收口版并授权实施
- 券商授权：无；不连接 MiniQMT，不提交或撤销订单

## 目标

把现有两个安全命令收敛为一个依赖明确、可恢复、可重复的日常运行入口：

```text
运行窗口与本地恢复检查
→ WP-0025 日度数据提交
→ WP-0029 研究决策链
→ 备份/恢复就绪核验
→ 不可变 DailyRunSummary
```

`DailyRunSummary` 只汇总各步骤身份、状态、耗时、阻断码和下一恢复动作，不复制行情、
候选证券、账户或订单载荷。

## 范围

- 新增 `make daily-run`、`make daily-run-status` 和明确的恢复命令；
- 复用现有 SQLite/WAL、租约和检查点，不建立第二套任务系统；
- 固定同一次运行的目标交易日、数据提交、策略晋级和 Shadow 起点身份；
- `waiting_provider` 是可恢复等待，不得继续生成伪造的新研究链；
- 已完成步骤按身份复用；重启、重复调用和进程竞争不得产生第二份逻辑结果；
- 30 分钟日度预算耗尽后进入可见 `stale` 或 `blocked`；
- 最后按内容寻址发布不可变运行摘要，再原子更新当前摘要指针；
- API 请求和浏览器刷新不得直接触发 Tushare、研究重算或券商连接。

## 非目标

- 不安装系统计划任务；安装与开机恢复由 WP-0031 承接；
- 不增加可写界面；系统页操作由 WP-0032 承接；
- 不连接 MiniQMT，不读取账户，不推进 Shadow 周期；
- 不提交、撤销或查询恢复 Paper 订单，不启用 Live；
- 不训练模型，不进入长线、行业生命周期或 ETF。

## 允许修改

- `src/astramind_mini/local_ops/` 的日常运行编排、合同和同一控制库迁移；
- `src/astramind_mini/daily_decision.py` 的公开调用边界；
- `scripts/` 的单一入口；
- `Makefile`；
- 聚焦测试与直接文档。

## 高争用文件

- `Makefile`
- `src/astramind_mini/composition.py`
- `var/control` 对应的追加式迁移目录

## 契约与兼容性

- 新增内部冻结合同 `DailyRunStatus`、`DailyRunStep`、`DailyRunSummary`；
- 保持十个薄腰公共契约及现有 JSON Schema 不变；
- 摘要只引用 `DataSnapshot`、`FeatureSnapshot`、`PredictionBatch`、
  `PortfolioTarget` 和 `OrderPlan` 身份；
- `paper_dispatch_state=disabled`、`broker_actions_allowed=false` 为不可变字段。

## 验收

1. Given 最近完成交易日数据完整，When 运行 `make daily-run`，Then WP-0025 成功提交后
   才运行 WP-0029，并发布一份绑定全部身份的运行摘要。
2. Given 提供方数据尚未完整，When 运行，Then 状态保持 `waiting_provider`，研究决策链
   不推进，上一完整摘要仍可读取。
3. Given 在任一步骤后中断，When 使用相同运行身份恢复，Then 已完成步骤不重复，最终
   摘要身份与无中断运行一致。
4. Given 两个进程竞争或同一输入重复运行，When 检查控制库和产物，Then 只有一份逻辑
   结果，另一进程得到明确租约状态。
5. Given 日度预算耗尽或身份漂移，When 查看状态，Then 显示脱敏阻断码和准确恢复命令。
6. Given 扫描制品、日志和调用计数，Then MiniQMT、Paper/Live、Shadow 周期和券商写入
   次数均为零。
7. Given 更新日期已经存在，When 恢复或回放更早目标日期，Then 数据与决策步骤只读取
   该运行冻结的准确数据运行和提交身份，不把全局最新状态误判为本次结果；内层数据已
   完成时直接复用，不强制重抓。

## 检查

```text
uv run pytest tests/unit/test_daily_run_orchestrator.py
uv run pytest tests/integration/test_daily_pipeline_api.py
make check
git diff --check
```

## 实施结果

- `DailyRunStatus`、`DailyRunStep`、`DailyRunSummary` 已作为冻结内部合同落地；
- `DailyRunStore` 使用 SQLite/WAL 保存租约、当前状态、步骤检查点和不可变摘要索引，
  摘要按内容寻址发布后才原子更新当前指针；
- `make daily-run` 顺序复用 WP-0025、WP-0029 和既有外部备份能力，
  `daily-run-status` 只读状态，`daily-run-recover` 必须携带原运行身份；
- 已验证提供方等待不推进研究、完成步骤恢复不重复、备份失败关闭、并发租约、运行窗口
  和 30 分钟预算耗尽；
- 真实本地验收以 2026-07-28 为目标日成功绑定数据提交、决策链和
  `local-backup:23e9fc3b...`，发布
  `daily-run-summary:46b4b794...`；相同命令重跑直接返回同一摘要且不再执行上游；
- `make check` 通过：Python 177 项、前端 38 项，以及类型、构建、架构、文档、密钥和
  公共 Schema 检查全部通过；
- 全部摘要保持 `paper_dispatch_state=disabled`、券商连接/写入次数为零。
- 2026-07-29 逐触发器实测发现历史目标日会被全局最新数据状态遮蔽，外层进程仍以
  退出码0结束；v1.2 改为按 `base_snapshot_id + target_date` 精确解析数据运行，
  保存不可变 `DailyPipelineCommit` 历史，并把准确数据运行身份传入决策链。已有
  更新日期时，历史恢复不再依赖全局 latest 或当前指针。

## 交接

- 下一工作包：WP-0031；
- 本工作包已单独批准；WP-0031、WP-0032 仍需分别批准；
- 完成不等于安装计划任务，也不改变任何券商授权。

## 版本历史

| 版本 | 日期 | 变更 | 状态 |
| --- | --- | --- | --- |
| 1.0.0 | 2026-07-28 | 登记 Daily Ops 1.0 第一里程碑草案 | 草案 |
| 1.1.0 | 2026-07-28 | 对齐 REQ-0009/WP-0025 事件日更边界，冻结并完成八小时收口范围 | 已完成 |
| 1.2.0 | 2026-07-29 | 修复更新日期存在时历史目标日的数据提交与决策链精确身份恢复 | 已完成 |
