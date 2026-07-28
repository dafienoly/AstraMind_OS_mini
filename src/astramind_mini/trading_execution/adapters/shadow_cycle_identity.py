"""Canonical persistence identities for Shadow cycle evidence."""

from __future__ import annotations

from ..contracts.shadow_cycle import ShadowCycleCheckpoint, ShadowCycleResult


def checkpoint_identity(value: ShadowCycleCheckpoint) -> dict[str, object]:
    return {
        "cycle_id": value.cycle_id,
        "data_snapshot_id": value.data_snapshot_id,
        "trading_date": value.trading_date,
        "phase": value.phase,
        "status": value.status,
        "state_id": value.state_id,
        "sessions_elapsed": value.sessions_elapsed,
        "entry_order_plan_id": value.entry_order_plan_id,
        "exit_order_plan_id": value.exit_order_plan_id,
        "event_count": value.event_count,
        "market_evidence_hash": value.market_evidence_hash,
        "blocker_codes": value.blocker_codes,
        "recorded_at": value.recorded_at,
    }


def result_identity(value: ShadowCycleResult) -> dict[str, object]:
    return {
        "cycle_id": value.cycle_id,
        "status": value.status,
        "initial_state_id": value.initial_state_id,
        "terminal_state_id": value.terminal_state_id,
        "entry_date": value.entry_date,
        "exit_date": value.exit_date,
        "sessions_elapsed": value.sessions_elapsed,
        "initial_equity_cny": value.initial_equity_cny,
        "terminal_equity_cny": value.terminal_equity_cny,
        "total_return": value.total_return,
        "realized_profit_cny": value.realized_profit_cny,
        "maximum_drawdown": value.maximum_drawdown,
        "checkpoint_count": value.checkpoint_count,
        "execution_event_count": value.execution_event_count,
        "completed_at": value.completed_at,
    }


__all__ = ["checkpoint_identity", "result_identity"]
