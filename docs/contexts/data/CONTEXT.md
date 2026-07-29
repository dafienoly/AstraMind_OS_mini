# Data

The Data context defines what the system knew, when it knew it, and which immutable
dataset version downstream research consumed.

## Language

**Observation**:
A provider-sourced fact associated with both a market/economic date and an availability
time.
_Avoid_: Row, current value

**Availability Time**:
The earliest timestamp at which an observation may be used by the system without
look-ahead.
_Avoid_: Report period, effective date

**Raw Record**:
An append-only representation of the provider response before semantic normalization.
_Avoid_: Clean data

**Normalized Dataset**:
A typed, deduplicated collection of observations with explicit units, source identity,
and availability semantics.
_Avoid_: Gold, latest table

**Data Snapshot**:
An immutable, versioned view of every dataset used by one research or trading request.
_Avoid_: Latest data, database state

**Point-in-Time Join**:
A relationship that selects only observations whose availability time is no later than
the consuming decision time.
_Avoid_: Forward fill

**Feature Snapshot**:
An immutable set of derived values linked to exactly one data snapshot, feature
definition version, and as-of time.
_Avoid_: Factor table, model input file

**Data Semantics Version**:
An immutable mapping from provider fields and corporate-action facts to research price,
raw execution price, volume, amount, turnover, market capitalization, and availability
meaning.
_Avoid_: Adjustment option, current convention

**Feature Availability State**:
One of observed, missing, or not-applicable, stored separately from a feature's numeric
model view and imputation indicators.
_Avoid_: Null-or-zero, filled value

**Market Feed Session**:
A versioned interval of provider connectivity, entitlement, subscriptions, message
timing, gaps, and recovery for a realtime market feed.
_Avoid_: Live data, socket

**Provider Cache**:
Provider-managed local files used to serve or recover observations, never the identity
of a published data snapshot.
_Avoid_: Database, current truth

**Canonical Dataset Request**:
A provider-neutral request for one named dataset, frozen universe, time range, fields,
frequency, adjustment convention, and point-in-time policy.
_Avoid_: Tushare API call, MiniQMT query

**Dataset Source Route**:
An immutable run-scoped ordering of primary and fallback providers plus timeout,
schema, and quality-gate identity for one canonical dataset.
_Avoid_: Current provider switch, per-row fallback

**Source Selection Evidence**:
Append-only proof of the chosen provider, rejected attempts, fallback reason, latency,
and normalized content identity for one dataset request.
_Avoid_: Provider log, retry message

**Realtime Microbatch**:
An immutable, content-addressed bundle of raw feed messages and separately normalized
observations linked to one market-feed session.
_Avoid_: Live table, latest quote file

**Current-Session Projection**:
A refreshable, explicitly provisional view derived from append-only realtime
microbatches and linked to one market-feed session plus the last completed reference
snapshot.
_Avoid_: Today's data snapshot, final daily bar

**Candidate-Scoped Intraday Request**:
A canonical minute/tick request whose candidate universe, evidence cutoff, fields,
frequency, lookback, and quality policy were frozen by an upstream coarse-screening
identity before any intraday values were inspected.
_Avoid_: Manual watchlist download, strategy SDK call

**Session-Sealed Intraday Dataset**:
An immutable normalized minute/tick dataset with provider, retrieval time, market time,
session identity, coverage, gaps, and content hash, eligible for a data snapshot only
after its declared cutoff has been sealed.
_Avoid_: Realtime projection, provider cache
