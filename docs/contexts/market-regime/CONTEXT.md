# Market Regime

The Market Regime context describes broad-market and industry conditions without
creating trading instructions.

## Language

**Market Dashboard**:
A broad-market view of index direction, breadth, liquidity, price-limit activity,
style, and risk conditions.
_Avoid_: Home page, index screen

**Industry Dashboard**:
A comparable cross-industry view of strength, breadth, liquidity, valuation context,
and lifecycle state.
_Avoid_: Sector list, heatmap

**Provisional Intraday Market View**:
A current-session broad-market or industry projection whose feed session, freshness,
gaps, and last completed daily reference are explicit. It may explain today's market
but does not rewrite an official daily regime or lifecycle snapshot.
_Avoid_: Current daily close, intraday lifecycle fact

**Stock Inspection Focus**:
A read-only identity envelope for one A-share at an evidence cutoff, carrying its
origin and optional comparison cohort, strategy, or portfolio references so every
entry point can open the same stock workbench without transferring ownership of facts.
_Avoid_: Selected stock, local drill-down state, stock detail DTO

**Market Regime**:
A versioned description of the prevailing market environment and its confidence.
_Avoid_: Market prediction, bull/bear truth

**Model Activation**:
A content-addressed read-only pointer selecting which exact market model or deterministic
baseline a projection presents. It may update or fall back under recorded evidence
rules but never authorizes a strategy, portfolio, order, or broker action.
_Avoid_: Strategy promotion, deployment, automatic trading

**Model Prediction Context**:
The exact model, feature snapshot, data snapshot, prediction horizon, evidence state,
and fallback reason attached to a Market Regime projection alongside its raw structural
evidence.
_Avoid_: AI score, current model

**Industry Lifecycle Snapshot**:
A point-in-time description of an industry's structural strength, participation,
transition state, confidence, and supporting evidence.
_Avoid_: Industry recommendation, ETF signal

**Strong Participation (S)**:
The percentage of point-in-time valid industry members whose versioned position and
trend scores jointly satisfy the strong structural state.
_Avoid_: Capital inflow, buy ratio

**Low-position Repair Participation (L)**:
The percentage of point-in-time valid industry members whose low price position and
improving relative structure jointly satisfy the repair state.
_Avoid_: Bottom signal, rebound guarantee

**ETF Direction**:
A versioned mapping from one or more industry exposures to a tradable ETF candidate
set.
_Avoid_: ETF order, static binding

**ETF Rotation Candidate**:
An ETF direction that passed lifecycle, relative-strength, liquidity, and tradability
screening but has not yet become a portfolio target.
_Avoid_: ETF trade
