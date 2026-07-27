# Trading Execution

The Trading Execution context turns portfolio intent into auditable orders while
keeping local simulation and real-broker effects distinct.

## Language

**Order Plan**:
An immutable proposal describing the orders required to move from current holdings to
a portfolio target.
_Avoid_: Trade, signal

**Standing Mandate**:
A user-approved envelope of strategies, capital, instruments, order types, timing, and
risk limits inside which routine execution needs no repeated approval.
_Avoid_: Auto-trading switch, blanket approval

**Approval Exception**:
An order-plan or mandate condition that requires human attention because it is outside
the standing mandate or represents abnormal risk.
_Avoid_: Manual gate

**Shadow Execution**:
A local execution against recorded or live market observations that creates no broker
side effect.
_Avoid_: Paper, simulated broker

**Broker Gateway**:
The isolated adapter that translates order plans and broker events without owning
strategy or portfolio decisions.
_Avoid_: Execution engine

**Paper Execution**:
An execution acknowledged by a broker-provided simulated environment, distinct from
local Shadow.
_Avoid_: Shadow

**Live Execution**:
An execution that can create, change, or close a real capital position.
_Avoid_: Production, enabled

**Execution Event**:
An immutable fact about submission, acknowledgement, fill, rejection, cancellation, or
reconciliation.
_Avoid_: Log line

**Account Snapshot**:
A read-only, as-of view of cash, positions, orders, trades, account mode, and
reconciliation identity with credentials and broker account identifiers removed.
_Avoid_: Current account, broker response

**Startup Reconciliation**:
A fail-closed comparison of local execution projections with broker account, position,
open-order, and trade facts before new broker actions are allowed.
_Avoid_: Sync, refresh

**Shadow Ledger**:
An append-only local SQLite/WAL record of Shadow execution events, with idempotent
replay and no broker side effect.
_Avoid_: Broker order table
