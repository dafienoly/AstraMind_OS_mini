"""Pure Trading Execution domain logic."""

from .continuous_shadow import (
    assess_drawdown,
    build_continuous_shadow_order_plan,
    initial_continuous_shadow_state,
    isolate_broker_simulation_state,
    start_continuous_shadow_cycle,
)
from .continuous_shadow_lifecycle import apply_shadow_fills, roll_shadow_trading_day
from .reconciliation import canonical_hash, reconcile_account, synthetic_shadow_projection

__all__ = [
    "apply_shadow_fills",
    "assess_drawdown",
    "build_continuous_shadow_order_plan",
    "canonical_hash",
    "initial_continuous_shadow_state",
    "isolate_broker_simulation_state",
    "reconcile_account",
    "roll_shadow_trading_day",
    "start_continuous_shadow_cycle",
    "synthetic_shadow_projection",
]
