# WP-0043：ETF 研究数据基础与候选资格

- 状态：完成（实现、正式发布并接入日度原子更新）
- 需求：REQ-2026-0008 v1.9.0
- 阶段：6E
- UI：不适用；本包不新增或修改用户界面
- 授权：ETF 数据只读采集、规范化、不可变发布和研究资格检查

## 目标

建立可重建的 ETF 主表、日线、份额和 SW2021 L1 映射数据产品，使后续轮动公式能够
在一个 `DataSnapshot` 内区分价格确认、上下文代理、数据不足和不可用，而不是从基金
名称临时猜测标的。

## 非目标

- 不计算 ETF 轮动分、目标权重或调仓结果；
- 不实现 UI-PROP-0009；
- 不形成 `PortfolioTarget`、`OrderPlan`、Research Shadow、MiniQMT Paper 或 Live；
- 不复制旧系统 22 个方向注册表，也不把当前映射倒灌为历史已知事实；
- 不用成交额替代价差或跟踪误差并宣称策略门禁通过。

## 首版冻结

- 映射版本：`sw2021-l1-etf-mapping-v1.0.0`；
- 映射自 2026-07-29 起有效，历史价格只用于特征预热；注册日前不得宣称点时策略结果；
- 只使用明确白名单代码，禁止名称模糊扩充；
- `exact` 可进入候选资格，`subindustry/composite_proxy/theme_context` 只作为上下文，
  `unavailable` 保留行业身份和缺口；
- 基础资格：上市满 252 个完成交易日、最近 20 日成交额中位数不低于 2,000 万元、
  最新份额乘收盘价不低于 1 亿元、证据不陈旧；
- 价差、跟踪误差、申赎和停牌/可交易性仍是后续策略包的强制门禁；本包不会把
  `foundation_eligible` 命名为策略合格。

## 允许文件

- `src/astramind_mini/data/etf_foundation/**`
- `scripts/publish_etf_foundation.py`
- `tests/unit/test_etf_foundation.py`
- `tests/integration/test_etf_foundation_publication.py`
- 本工作包及直接引用的需求、计划、数据合同、决策日志和追踪索引

## 受影响合同

- `EtfMasterObservation`
- `EtfDailyObservation`
- `EtfShareObservation`
- `EtfIndustryMappingObservation`
- `EtfFoundationQualification`

数据集名称固定为 `etf_master`、`etf_daily`、`etf_share` 和
`etf_industry_mapping`。原始提供方记录和四个规范数据集分开保存。

## 验收

1. 白名单代码必须由 ETF 主表逐一确认；缺失、重复或非上市状态失败关闭；
2. 日线和份额按市场日期及可用时间规范化，单位明确；
3. 映射覆盖全部 31 个 L1；无可靠 ETF 的行业显示 `unavailable`；
4. 资格计算只能读取截止日及以前的日线、份额和映射，注册日后才允许形成候选资格；
5. 覆盖不足、规模不足、流动性不足、陈旧和代理映射分别给出拒绝原因；
6. 发布形成新的不可变 `DataSnapshot`，可选择激活但不触碰券商或交易状态；
7. 领域、规范化、发布、点时和负面边界有聚焦自动化证明。

## 保护边界

本包只提供数据事实和基础资格。后续 ETF 轮动必须另行冻结公式、周度决策日、
下一交易日执行、成本、价差、跟踪误差、样本外区间和 Paper 候选边界。

## 实施结果

- 已在独立 `data.etf_foundation` 包实现五类严格合同、31 个 SW2021 L1 身份和
  32 条版本化映射记录；
- 已实现 Tushare 原始响应保留、ETF 主表/日线/份额规范化、四数据集不可变发布和
  基础 `DataSnapshot` 组合；
- 已实现截止日过滤、映射生效日、上市历史、20 日成交额、规模、陈旧和代理降级；
  所有结果固定 `strategy_gate_ready=false`；
- ETF 主表和份额没有可审计历史发布日期时按实际检索时间可用，不把上市日或份额
  对应交易日冒充历史可用时间；
- 请求截止日尚无提供方 ETF 日线时允许发布数据底座，但必须在快照中传播
  `etf_daily_latest_before_requested_cutoff`，资格统一降级为 `stale`；
- 已提供 `publish_etf_foundation.py`，默认不执行券商动作，只有显式 `--activate`
  才激活新快照；
- 已提供 `restore_etf_snapshot.py`，只从最近完整的不可变 ETF 快照恢复四个数据集到
  当前快照，不联网、不改写旧版本；激活同样要求当前指针仍等于冻结基础；
- 聚焦校验通过：Ruff、Mypy、5 个单元测试和 1 个真实文件系统集成测试；
- 用户授权将既有本机 Tushare 配置迁入 Git 忽略的 `.env.local`，文件权限为 `0600`；
  未复制其他旧项目配置，也未在日志或文档中记录 token；
- 正式发布并激活
  `snapshot:sha256:94a33a3c8ef6ad67e9faf7e844d8dce02e64e0004b3ac05a95ffcd09daf1831d`：
  28 只 ETF 主表、34,655 条日线、34,803 条份额和 32 条映射，账本与当前指针复验
  通过；
- 2026-07-29 是交易日，但发布时提供方 ETF 日线只到 2026-07-28。快照显式记录
  `etf_daily_latest_before_requested_cutoff`，20 条 `exact` 映射全部为 `stale`，
  另有 9 条 `context_only`、3 条 `unavailable`；没有策略合格对象。
- 日度旧基线覆盖事件修复后，当前快照为
  `snapshot:sha256:665425787308c4e239cb735720a874ac41eaa7275565988b303b291c31d59a47`，
  重新包含四个 ETF 数据集；真实 API 返回 32 条候选事实，页面显示 29 只有代码的
  映射标的及“证据陈旧”，不再显示“ETF 研究不可用”。
- 2026-07-29 晚间修复将四个 ETF 数据集作为 WP-0025 日度管线扩展，在最终
  `DataSnapshot` 指针切换前与行业、宽基和事件一起提交；18:05 前明确
  `waiting_provider`，20:10 计划触发负责最终恢复。新鲜日线会解析并移除
  `etf_daily_latest_before_requested_cutoff`，不会因快照日期较新而掩盖旧数据集。
