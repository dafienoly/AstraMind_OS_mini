# Context Map

## Contexts

- [Data](./docs/contexts/data/CONTEXT.md) — owns source observations, point-in-time
  availability, normalized datasets, and immutable snapshots.
- [Market Regime](./docs/contexts/market-regime/CONTEXT.md) — describes broad-market
  and industry state, including lifecycle and ETF direction evidence.
- [Strategy Research](./docs/contexts/strategy-research/CONTEXT.md) — turns feature
  snapshots into versioned strategy candidates, comparable evidence, and isolated
  multi-candidate Research Shadow evidence.
- [Portfolio & Risk](./docs/contexts/portfolio-risk/CONTEXT.md) — converts selected
  forecasts into portfolio targets under capital and drawdown constraints.
- [Trading Execution](./docs/contexts/trading-execution/CONTEXT.md) — converts approved
  targets into order plans, supports deterministic Local Replay, and records single-
  account Paper or Live execution events.

## Relationships

- **Data → Market Regime**: a `DataSnapshot` supplies market, industry, ETF, and
  constituent observations for an `IndustryLifecycleSnapshot`.
- **Data → Strategy Research**: a `DataSnapshot` and its derived `FeatureSnapshot`
  provide the only valid research inputs.
- **Strategy Research → Data**: an immutable `CoarseScreeningBatch` may scope a
  provider-neutral intraday data request; strategy code never calls MiniQMT directly,
  and only a session-sealed dataset may return through a new `DataSnapshot`.
- **Market Regime → Strategy Research**: regime and lifecycle snapshots are contextual
  features; they do not place orders.
- **Strategy Research → Portfolio & Risk**: a `StrategyVersion` emits predictions and
  historical or Research Shadow evidence, never broker instructions.
- **Portfolio & Risk → Trading Execution**: a `PortfolioTarget` becomes an `OrderPlan`
  after sleeve, account-risk, and mandate evaluation; Paper sleeve projections never
  replace broker account facts.
- **Trading Execution → Strategy Research / Portfolio & Risk**: immutable
  `ExecutionEvent` records support attribution and review without rewriting research
  history.
