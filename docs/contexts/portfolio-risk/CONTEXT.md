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

**Virtual Horizon Budget**:
A fixed analytical share of a sleeve assigned to one forecast horizon before both
horizons are consolidated into one portfolio target; an unusable budget remains cash.
_Avoid_: Separate account, dynamic model weight

**Core Policy Version**:
An immutable identity binding exact H20 and H60 strategy versions, their virtual
budgets, optimizer, costs, constraints, and risk rules into one core-sleeve policy.
_Avoid_: Model pair, optimizer config

**Active Sleeve Policy**:
The one exact policy version currently selected to create targets for a named sleeve.
Research challengers remain candidates and do not share its Paper capital.
_Avoid_: All active strategies, candidate pool

**Paper Sleeve Projection**:
An internal budget and managed-position view for one sleeve inside the single broker
simulation account. It is not a broker subaccount or an independent cash truth.
_Avoid_: Paper account, subaccount

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
