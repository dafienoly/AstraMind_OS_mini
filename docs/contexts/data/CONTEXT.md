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

**Market Feed Session**:
A versioned interval of provider connectivity, entitlement, subscriptions, message
timing, gaps, and recovery for a realtime market feed.
_Avoid_: Live data, socket

**Provider Cache**:
Provider-managed local files used to serve or recover observations, never the identity
of a published data snapshot.
_Avoid_: Database, current truth

**Realtime Microbatch**:
An immutable, content-addressed bundle of raw feed messages and separately normalized
observations linked to one market-feed session.
_Avoid_: Live table, latest quote file
