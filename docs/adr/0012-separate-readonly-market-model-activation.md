---
status: accepted
---

# ADR-0012：只读市场模型激活与策略晋级分离

大盘热力、行业相对轮动、生命周期、行业内研究顺序和 ETF 轮动可以使用学习模型，
但它们仍属于 Market Regime 的只读上游证据。系统为这类模型建立独立的
`MarketModelManifest`、`MarketModelEvidenceBundle`、`ModelValidationSummary` 和
`ModelActivation`；它们不能创建 `PortfolioTarget`、`OrderPlan`、`ExecutionEvent`
或券商权限。

`ModelActivation` 只是某个页面投影当前采用哪一个准确方法版本的内容寻址指针。
它不等同于 Strategy Research 的 Promotion、Renewal 或 Fallback，也不授权
Research Shadow、MiniQMT Paper、Live 或真实资金。任何把市场研究升级为可执行策略的
决定仍需独立需求、策略版本、组合风险和明确用户授权。

每个学习模型必须保留一个可重建的规则式 v1 作为解释基线和失败关闭回退：

- 新模型只读追加新方法身份，不能覆盖或改写 v1 快照；
- 初始 v2 可以在正确性、覆盖和准确 UI 获批后以 `unvalidated` 展示；
- 封存证据不支持、模型产物损坏、输入快照不兼容或覆盖下降时，页面指针自动回到
  准确 v1，且必须显示回退原因；
- 月度挑战者只有在点时验证、风险、成本和换手均不差于在位模型时才可更新只读指针；
- ETF v2 还必须通过官方基准、NAV/可交易性和真实 L1 价差的前向门禁，未通过前不得
  激活。

自动回退只改变只读页面方法，不产生卖出、调仓或风险动作。历史预测、激活、回退和
证据记录只追加保存，当前指针只是可恢复视图。

学习模型由 Strategy Research 拥有训练、验证和产物；Market Regime 只通过公共契约
消费准确预测和激活状态，再与同一个 `DataSnapshot` 的原始结构证据组成页面投影。
Data 继续拥有原始观察、标准化数据和不可变快照，任何模型不得建立第二份行情或成员
关系真相。
