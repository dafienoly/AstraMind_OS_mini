# Context Map

## Contexts

- [Data](./docs/contexts/data/CONTEXT.md) — owns source observations, point-in-time
  availability, normalized datasets, and immutable snapshots.
- [Market Regime](./docs/contexts/market-regime/CONTEXT.md) — describes broad-market
  and industry state, including lifecycle and ETF direction evidence.
- [Strategy Research](./docs/contexts/strategy-research/CONTEXT.md) — turns feature
  snapshots into versioned strategy candidates and comparable evidence.
- [Portfolio & Risk](./docs/contexts/portfolio-risk/CONTEXT.md) — converts selected
  forecasts into portfolio targets under capital and drawdown constraints.
- [Trading Execution](./docs/contexts/trading-execution/CONTEXT.md) — converts approved
  targets into order plans and records Shadow, Paper, or Live execution events.

## Relationships

- **Data → Market Regime**: a `DataSnapshot` supplies market, industry, ETF, and
  constituent observations for an `IndustryLifecycleSnapshot`.
- **Data → Strategy Research**: a `DataSnapshot` and its derived `FeatureSnapshot`
  provide the only valid research inputs.
- **Market Regime → Strategy Research**: regime and lifecycle snapshots are contextual
  features; they do not place orders.
- **Strategy Research → Portfolio & Risk**: a `StrategyVersion` emits predictions and
  evidence, never broker instructions.
- **Portfolio & Risk → Trading Execution**: a `PortfolioTarget` becomes an `OrderPlan`
  after risk and mandate evaluation.
- **Trading Execution → Strategy Research / Portfolio & Risk**: immutable
  `ExecutionEvent` records support attribution and review without rewriting research
  history.
