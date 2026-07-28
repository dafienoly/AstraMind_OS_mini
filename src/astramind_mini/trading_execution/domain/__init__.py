"""Pure Trading Execution domain logic."""

from .continuous_shadow import (
    assess_drawdown,
    build_continuous_shadow_order_plan,
    initial_continuous_shadow_state,
    isolate_broker_simulation_state,
    start_continuous_shadow_cycle,
)
from .continuous_shadow_lifecycle import (
    apply_shadow_fills,
    mark_shadow_to_market,
    roll_shadow_trading_day,
)
from .paper import (
    apply_paper_observation,
    build_paper_intent,
    build_paper_preflight,
    initial_paper_projection,
    replay_paper_observations,
)
from .paper_canary import build_paper_canary_authorization
from .paper_continuous import build_paper_limit_proposal, validate_submission_approval
from .paper_runtime import (
    account_drawdown,
    build_convergence_report,
    build_paper_canary_order_plan,
    build_real_paper_preflight,
    build_submission_approval,
)
from .paper_startup import (
    build_callback_handshake,
    build_mode_lock,
    build_paper_account_baseline,
)
from .reconciliation import canonical_hash, reconcile_account, synthetic_shadow_projection

__all__ = [
    "account_drawdown",
    "apply_paper_observation",
    "apply_shadow_fills",
    "assess_drawdown",
    "build_callback_handshake",
    "build_continuous_shadow_order_plan",
    "build_convergence_report",
    "build_mode_lock",
    "build_paper_account_baseline",
    "build_paper_canary_authorization",
    "build_paper_canary_order_plan",
    "build_paper_intent",
    "build_paper_limit_proposal",
    "build_paper_preflight",
    "build_real_paper_preflight",
    "build_submission_approval",
    "canonical_hash",
    "initial_continuous_shadow_state",
    "initial_paper_projection",
    "isolate_broker_simulation_state",
    "mark_shadow_to_market",
    "reconcile_account",
    "replay_paper_observations",
    "roll_shadow_trading_day",
    "start_continuous_shadow_cycle",
    "synthetic_shadow_projection",
    "validate_submission_approval",
]
