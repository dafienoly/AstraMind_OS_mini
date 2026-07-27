# Strategy Research

The Strategy Research context defines testable trading hypotheses, comparable
evidence, and controlled promotion between research states.

## Language

**Strategy Logic**:
A coherent hypothesis that maps a feature snapshot to predictions, entries, exits, and
risk intent.
_Avoid_: Indicator, script

**Strategy Version**:
An immutable identity covering logic, parameters, feature definitions, model artifact,
universe, and execution assumptions.
_Avoid_: Current strategy, config

**Strategy Candidate**:
A strategy version under evaluation that has not been authorized for a capital sleeve.
_Avoid_: Active strategy

**Strategy Arena**:
The comparison space where independent strategy families compete on the same evidence
and cost assumptions.
_Avoid_: Leaderboard

**Sealed Replay**:
An evaluation on a deliberately hidden historical interval that cannot be used to tune
the evaluated strategy version.
_Avoid_: Shadow, validation backtest

**Champion**:
The strategy version currently selected for a defined sleeve, horizon, and mandate.
_Avoid_: Best strategy

**Challenger**:
A strategy candidate evaluated against the champion without silently replacing it.
_Avoid_: Experimental champion

**Promotion**:
An explicit decision that changes which strategy version may create portfolio targets
for a named sleeve.
_Avoid_: Deploy, enable

**Universe Decision**:
A point-in-time eligibility result with explicit seasoning, risk-state, tradability,
liquidity, and coverage reasons.
_Avoid_: Current stock pool

**Backtest Event**:
An immutable signal, fill, rejection, or exit fact recorded by the common execution
assumptions during research.
_Avoid_: Print statement, trade result
