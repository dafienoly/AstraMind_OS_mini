# Portfolio & Risk

The Portfolio & Risk context allocates capital across selected ideas and limits the
damage one strategy, position, or regime can cause.

## Language

**Sleeve**:
A separately budgeted part of the account with its own horizon, strategy set, and risk
limits.
_Avoid_: Account, strategy balance

**Tactical Sleeve**:
The CNY 50,000 sleeve for short-horizon individual-stock strategies, normally holding
one or two names.
_Avoid_: Short account

**Core Sleeve**:
The CNY 100,000 sleeve for weekly evaluated individual-stock portfolios, normally
holding about five names.
_Avoid_: Long account

**Optimization Problem**:
A versioned set of forecasts, constraints, costs, holdings, and risk budgets submitted
to an optimizer.
_Avoid_: Weight calculation

**Optimization Result**:
The optimizer's proposed target weights and diagnostics, linked to exactly one
optimization problem.
_Avoid_: Portfolio

**Portfolio Target**:
The desired holdings after portfolio construction and risk evaluation, before order
generation.
_Avoid_: Order list

**Risk Budget**:
The maximum planned exposure to a named source of loss, including sleeve, position,
industry, liquidity, and drawdown risk.
_Avoid_: Stop loss

**Drawdown Gate**:
A recorded response rule triggered by portfolio peak-to-trough loss at the accepted
8%, 10%, and 12% control levels.
_Avoid_: Guaranteed loss limit

**Tactical Target Details**:
The rebuildable holdings, reference prices, weights, and cash weight associated with
one tactical Portfolio Target.
_Avoid_: Order list
