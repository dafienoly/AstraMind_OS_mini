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

**Strategy Lineage**:
A stable identity for one feature meaning, selection set, training recipe, and model
family across scheduled retraining events.
_Avoid_: Latest model, strategy name

**Lineage Evidence Version**:
An immutable evidence identity built from the exact out-of-fold model artifacts that
actually existed in each historical fold.
_Avoid_: Backfilled current model performance

**Strategy Candidate**:
A strategy version under evaluation that has not been authorized for a capital sleeve.
_Avoid_: Active strategy

**Coarse Screening Batch**:
An immutable full-market daily screening result that freezes the ranked shortlist,
evidence cutoff, and screening version before candidate-scoped intraday data is
requested.
_Avoid_: Watchlist, current top picks

**Intraday Validation Snapshot**:
Immutable candidate-level evidence built from a session-sealed intraday dataset for
every member of one coarse screening batch. Its first-release outcome is validated,
vetoed, or inconclusive and does not silently rerank the shortlist.
_Avoid_: Chart review, second model score

**Two-Stage Tactical Candidate**:
A strategy version whose identity covers both the daily coarse screen and the
versioned intraday validation recipe, evaluated end to end against its daily-only
parent.
_Avoid_: Daily strategy with an optional filter

**Strategy Arena**:
The comparison space where independent strategy families compete on the same evidence
and cost assumptions.
_Avoid_: Leaderboard

**Sealed Replay**:
An evaluation whose candidate roster and recipes are frozen before the interval is
opened for that evaluation. If the interval already existed before freezing, the
evidence must disclose that it is candidate-frozen rather than claim it was historically
unseen.
_Avoid_: Shadow, truly prospective evidence

**Research Shadow**:
A broker-free forward research observation of an exact frozen strategy version against
market data arriving after registration, with an isolated virtual ledger per candidate.
It supports candidate comparison but is neither an execution mode nor Paper maturity.
_Avoid_: Local Replay, Paper account, simulated broker

**Research Shadow Evidence**:
Immutable candidate evidence that preserves registration time, eligible decision dates,
point-in-time inputs, executable assumptions, failures, and independent virtual-ledger
results.
_Avoid_: Paper Evidence, broker fills, backfilled Shadow

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

**Renewal**:
An explicit decision to accept a newly trained exact strategy version within an
unchanged strategy lineage.
_Avoid_: Automatic refresh, promotion

**Fallback**:
An explicit, reasoned decision to return to a compatible permanent anchor or prior
champion after the selected version becomes unusable.
_Avoid_: Runner-up substitution, automatic rollback

**Market Model Manifest**:
An immutable read-only model identity for a Market Regime prediction, binding its data,
features, target, training recipe, artifact, dependency versions, and evidence windows.
It is not a strategy version and cannot create capital targets.
_Avoid_: Market strategy, latest model

**Market Model Evidence Bundle**:
Immutable development, candidate-frozen replay, audit, and prospective data-gate
evidence for one exact market model manifest.
_Avoid_: Strategy promotion evidence, Paper performance

**Universe Decision**:
A point-in-time eligibility result with explicit seasoning, risk-state, tradability,
liquidity, and coverage reasons.
_Avoid_: Current stock pool

**Backtest Event**:
An immutable signal, fill, rejection, or exit fact recorded by the common execution
assumptions during research.
_Avoid_: Print statement, trade result
