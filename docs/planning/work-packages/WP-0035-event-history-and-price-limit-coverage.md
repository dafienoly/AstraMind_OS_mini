# WP-0035：事件历史连续化与早期涨跌停覆盖核验

- 版本：1.0.0
- 状态：已完成
- 需求：REQ-2026-0005 v1.1.0、REQ-2026-0009 v1.2.0
- 阶段：2、3、7
- UI 提案：不适用；不新增或改变页面
- 日期：2026-07-28
- 来源：用户明确同意“先延伸 2026 事件并纳入日更快照，再回填 2005–2022，最后实测
  2000–2006 涨跌停并据实发布或保留未知”
- 券商授权：无；只允许 Tushare 行情/资料只读调用

## 目标

让龙虎榜、席位和股东户数从一次性封存数据变成日度生产快照中的连续事件数据，并把
2005–2022 历史回填为可恢复、可审计的准确版本；对 2000–2006 涨跌停逐交易日探测，
只有完整覆盖验证通过后才允许另行发布补齐版本。

## 非目标

- 不重新训练、调参、重跑封存证据或改变既有晋级决定；
- 不把 2023–2025 封存结果描述为 Live 或真正前瞻表现；
- 不根据昨收与固定百分比伪造早期涨跌停价；
- 不在日度关键路径执行 2005–2022 长历史回填；
- 不读取 MiniQMT 账户，不创建 Shadow/Paper/Live 动作或订单；
- 不实施 UI。

## 允许文件

- `src/astramind_mini/data/application/` 的事件增量、精确版本合并和覆盖探测；
- `scripts/backfill_tactical_events.py`、新的只读涨跌停探测入口；
- `scripts/run_daily_data_pipeline.py` 的日更组合入口；
- `Makefile` 的显式命令；
- 直接聚焦测试；
- REQ-2026-0005/0009、数据契约、计划、决策记录和本地运行指南。

## 高争用文件

- `Makefile`
- `src/astramind_mini/data/application/daily_pipeline.py`
- `docs/data/data-contracts.md`
- `docs/planning/phased-implementation-plan.md`
- `docs/requirements/README.md`

## 上下文与契约

- 受影响上下文：Data、Strategy Research；
- 公共契约：不改变 `DataSnapshot`、事件观察或策略契约 Schema；
- 兼容性：历史数据产生新 `DatasetManifest` 和 `DataSnapshot`，不改写旧版本；
- 事件可用时间：龙虎榜为交易日盘后；股东户数按公告日与报告期末较晚者；
- 日更事件实际完成探测采用 20:05 后保守窗口，16:30 仍是日度管线最早启动时间。

## 数据与点时影响

- 日更目标日同时查询 `top_list`、`top_inst` 和 `stk_holdernumber`；
- 原始响应只追加，标准化事件按 `source_record_hash` 去重；
- 每次增量固定基础事件版本，按年度合并并产生新内容身份；
- 2005–2022 是显式长回填，不进入默认 `make check`；
- 2000–2006 `stk_limit` 逐 SSE 交易日探测；任一交易日空响应、重复主键或范围外记录
  都禁止发布补齐版本；
- 探测报告本身不改变 `price_limit`、`DataSnapshot` 或 current 指针。

## 验收

1. Given 目标交易日已过 20:05 且事件接口完整，When 日度管线提交，Then 新
   `DataSnapshot` 同时包含目标日行情、行业和三个准确事件版本。
2. Given 尚未到事件保守完成窗口，When 运行日度管线，Then 状态为
   `waiting_provider`，现有生产提交不变。
3. Given 同一目标日或历史区间中断，When 以相同基础版本和范围重跑，Then 已完成请求
   不重复，年度合并无重复观察且身份确定。
4. Given 回填 2005–2022，When 与既有 2023–2026 事件版本合并，Then 旧观察不丢失，
   新快照只引用一个同名数据集版本。
5. Given 股东户数早期接口返回空窗口，When 发布覆盖清单，Then 空响应作为已探测覆盖
   保留，不把缺失户数填零或伪造公告。
6. Given 2000–2006 任一开市日 `stk_limit` 为空，When 探测完成，Then 报告为
   `historical_unavailable`，且 `publish_price_limit=false`。
7. Given 全部早期交易日均有唯一且范围正确的记录，When 探测完成，Then 只标记
   `backfill_ready`；实际发布仍使用独立、可审计的补齐步骤。
8. 所有产物保持 `broker_actions_allowed=false`，不产生账户或订单副作用。

## 检查

```text
uv run pytest tests/unit/test_tactical_event_backfill.py
uv run pytest tests/unit/test_daily_data_orchestration.py
uv run pytest tests/unit/test_historical_price_limit_probe.py
uv run mypy src/astramind_mini/data/application/
make docs-check
git diff --check
```

真实事件回填和 2000–2006 全交易日探测是显式联网长命令，不加入默认检查。
`make docs-check` 已包含密钥扫描。

## 真实验收

- 2026-07-28 日度生产运行已把三个事件版本纳入唯一 `DataSnapshot`，随后历史回填与
  既有 2023–2026 观察合并并发布
  `snapshot:sha256:c41e97132e8ba00ec15a8fb5bddbf67dd3a6d60f706e1aba7544b4b3922a7b1e`；
- 合并后龙虎榜 238,386 行、机构席位 2,534,436 行、股东户数 435,017 行；
- 2005–2022 共保存 9,904 个可恢复请求分区。龙虎榜最早真实观察为 2008 年，
  清单标记 `2005-2007` 提供方空年份；机构席位最早真实观察为 2012 年，清单标记
  `2005-2011` 提供方空年份；
- 原 AstraMind 正式 Silver 只有 2007-01-04 至 2026-07-24 的 `stk_limit`，没有
  `top_list`、`top_inst` 或 `stk_holdernumber` 制品；前者已迁入 Mini，后者不能从
  原库补齐；
- `stk_limit` 真实探测覆盖 2000–2006 的全部 1,683 个 SSE 开市日，1,683 日均为空。
  报告状态为 `historical_unavailable`，`publish_price_limit=false`，2007 年前继续
  保守标记未知；
- 全部验收保持 `broker_actions_allowed=false`，未连接 MiniQMT 或产生订单动作。

## 交接

- 2026 增量、2005–2022 回填和 2000–2006 探测均已完成；
- 保留 `price_limits_before_2007_unavailable`；
- 后续日度运行继续使用 20:05 保守事件完成门；
- 不触及 MiniQMT、账户和券商授权。
