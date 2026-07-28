"""Imports allowed for consumers of the Trading Execution context."""

from .contracts import ExecutionEvent, ExecutionMode, OrderPlan, StandingMandate
from .contracts.account import (
    AccountSnapshot,
    LocalAccountProjection,
    ReconciliationReport,
)
from .contracts.continuous_shadow import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ContinuousShadowState,
    DrawdownDecision,
    ReconciliationDisposition,
)
from .contracts.paper import (
    PaperBrokerObservation,
    PaperObservationKind,
    PaperOrderIntent,
    PaperOrderProjection,
    PaperOrderState,
    PaperPreflightDecision,
)
from .contracts.paper_canary import PaperCanaryAuthorization
from .contracts.paper_continuous import (
    PaperBrokerCommandResult,
    PaperLimitProposal,
    PaperOperationsSnapshot,
    PaperSubmissionApproval,
)
from .contracts.paper_runtime import PaperConvergenceReport
from .contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
    PaperStartupEvidence,
    ReadonlyCallbackHandshake,
)
from .contracts.shadow_cycle import ShadowCycleCheckpoint, ShadowCycleResult
from .domain.reconciliation import reconcile_account, synthetic_shadow_projection
from .domain.shadow import (
    OrderSide,
    ShadowFill,
    ShadowOrderLine,
    ShadowPortfolioState,
    ShadowPosition,
    ShadowQuote,
)

__all__ = [
    "AccountSnapshot",
    "BrokerAccountModeLock",
    "ContinuousShadowCycle",
    "ContinuousShadowOrderPlan",
    "ContinuousShadowState",
    "DrawdownDecision",
    "ExecutionEvent",
    "ExecutionMode",
    "LocalAccountProjection",
    "OrderPlan",
    "OrderSide",
    "PaperAccountBaseline",
    "PaperBrokerCommandResult",
    "PaperBrokerObservation",
    "PaperCanaryAuthorization",
    "PaperConvergenceReport",
    "PaperLimitProposal",
    "PaperObservationKind",
    "PaperOperationsSnapshot",
    "PaperOrderIntent",
    "PaperOrderProjection",
    "PaperOrderState",
    "PaperPreflightDecision",
    "PaperStartupEvidence",
    "PaperSubmissionApproval",
    "ReadonlyCallbackHandshake",
    "ReconciliationDisposition",
    "ReconciliationReport",
    "ShadowCycleCheckpoint",
    "ShadowCycleResult",
    "ShadowFill",
    "ShadowOrderLine",
    "ShadowPortfolioState",
    "ShadowPosition",
    "ShadowQuote",
    "StandingMandate",
    "reconcile_account",
    "synthetic_shadow_projection",
]
