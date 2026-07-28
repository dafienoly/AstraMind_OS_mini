# WP-0008：短线事件数据、封存证据与手动晋级

- 状态：已完成
- 需求：REQ-2026-0005 v1.0.0
- 阶段：阶段 2D／3
- UI 提案：不新增或修改页面；未来展示复用已批准的 UI-PROP-0004 v0.2
- 券商授权：无
- 日期：2026-07-27

## 目标

在一个不可变 `DataSnapshot` 上生产化龙虎榜、席位和股东户数数据，冻结三类短线策略
的九个版本，运行 2023–2025 全市场封存回放，并提供不带券商副作用的显式手动晋级
记录。

## 非目标

- 不实现策略竞技场产品页面；
- 不根据封存结果自动调参或自动选择冠军；
- 不伪造历史行业归属、市场状态拆解或“从未看过历史”的事实；
- 不读取 MiniQMT 账户，不启用 Shadow、Paper、Live，不创建订单；
- 不把真实长回填或全市场回放放入默认 `make check`。

## 允许文件

- `src/astramind_mini/data/**` 中的事件契约、标准化、发布和只读回填；
- `src/astramind_mini/strategy_research/**` 中的封存回放、证据和晋级；
- 对应 `scripts/`、`tests/`、`Makefile`；
- REQ-2026-0005、唯一追踪表、数据契约、阶段计划、决策记录、本地指南和当时的临时
  交接文件（现已[封存](../../archive/handoff-2026-07-28.md)）。

## 实施内容

1. 通过 Tushare 兼容 HTTP 接口按交易日可恢复回填 `top_list`、`top_inst`，按月回填
   `stk_holdernumber`；原始响应只追加保存，数值空值保持缺失。
2. 发布 `lhb_event`、`lhb_seat`、`shareholder_count` 三个不可变数据集，并从准确
   H4 基础快照派生新的 `DataSnapshot`。
3. 龙虎榜最早可用时间固定为交易日 18:00 Asia/Shanghai；股东户数通常按公告日
   18:00 可用，公告早于报告期末的异常记录保守取两者较晚日期；所有点时连接使用
   `available_at <= 决策时点`。
4. DuckDB 只读取快照清单列出的精确 Parquet，全市场计算上市交易日数、20 日流动性
   和三类候选信号，不接受 `latest` 或目录扫描。
5. 三类家族各冻结 2／5／10 周期版本；下一交易日开盘执行，应用 100 股整手、费用、
   滑点、成交额参与率、ST／停牌／涨跌停和最多两只持仓。
6. 封存证据记录逐笔成交与拒绝、权益曲线、年度结果、Sortino、Calmar、成本／容量
   版本、失败原因和已知限制。
7. SQLite/WAL 只追加记录用户明确的晋级或拒绝决定；决定必须精确匹配证据和策略版本，
   `broker_enabled` 恒为 `false`。

## 命令

真实回填与封存回放是显式长命令，不属于默认检查：

```text
make tactical-event-backfill \
  PROVIDER_ENV_FILE=/mnt/e/work/AstraMind_OS/.env \
  BASE_SNAPSHOT_ID=<H4 snapshot>

make tactical-sealed-replay SNAPSHOT_ID=<包含事件数据的 snapshot>
```

旧 `.env` 只读取允许的 Tushare 配置，不复制或打印 Token。结果写入 Git 忽略的
`var/data/` 和 `var/research/sealed/`。

## 验收

1. 晚于决策时点的观察不能进入历史事件上下文。
2. 相同原始输入与基础快照可恢复、幂等并产生相同数据集／快照身份。
3. 缺少事件数据集、发布未完成或存在关键缺口时，事件策略失败关闭。
4. 全市场扫描只读取准确快照清单路径；信号在下一交易日执行，受执行约束限制。
5. 同一候选集合与回放结果产生相同证据身份，创建时间不改变内容身份。
6. 晋级记录必须匹配准确证据和策略版本，重启后可恢复且不改变券商状态。
7. `make check`、Schema 漂移、密钥扫描和 `git diff --check` 通过。

## 受保护边界

本工作包没有 MiniQMT 交易适配器、账户标识、`StandingMandate` 实例、Paper／Live
状态或真实订单。完成证据不自动产生晋级决定；只有用户后续针对证据作出的明确选择
才能写入晋级账本。

## 实际结果

- 事件生产快照：
  `snapshot:sha256:a0042b6f7f15999a89bec8d4701f57ee000963d49fb6dcaca703454c296d20cc`；
- `lhb_event` 54,363 行，`lhb_seat` 558,698 行，`shareholder_count` 136,366 行；
- 真实回填发现股东户数空值、公告早于报告期末和月／周请求触顶，分别通过显式缺口、
  保守可用时间和有界二分分区处理，未填零、未发布截断响应；
- 九版本证据包：
  `evidence-bundle:sha256:9fdff6510b2eb65328066d1d815216ca8d83b689b3ccfec408cdba46b5f2f95e`；
- 九个版本均完成 2023–2025 全市场回放。只有反转／量价 10 日版本总收益为正
  （7.385%），但最大回撤为 58.811%；其余版本总收益均为负；
- 用户于 2026-07-28 将反转／量价 10 日版明确晋级为纯本地 Shadow 诊断挑战者；
  决定身份为
  `promotion:sha256:b33487a4042356161ea03fd3a4bd9c2a980629feea5ad49239fa2ec563334afd`；
  该决定明确披露低 Sharpe、高回撤和 2023 年亏损，不把它称为冠军或交易证明；
  `broker_enabled` 为 `false`；
- 真实快照与逐笔结果位于 Git 忽略的 `var/`，仓库只保留合成测试证据。
