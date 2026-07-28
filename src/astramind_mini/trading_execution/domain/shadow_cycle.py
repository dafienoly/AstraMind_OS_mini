"""Pure market-evidence and checkpoint logic for continuous Shadow."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.data.public import ShadowMarketObservation

from ..contracts.continuous_shadow import ContinuousShadowCycle, ContinuousShadowState
from ..contracts.shadow_cycle import (
    ShadowCycleCheckpoint,
    ShadowCycleStatus,
)
from .continuous_shadow_lifecycle import mark_shadow_to_market
from .reconciliation import canonical_hash
from .shadow import ShadowFill, ShadowQuote


def shadow_quotes(
    observations: tuple[ShadowMarketObservation, ...],
    side: Literal["buy", "sell"],
    open_at: datetime,
) -> dict[str, ShadowQuote]:
    result = {}
    for item in observations:
        if not item.has_daily_bar or item.open_price is None:
            continue
        price = item.open_price * (1.0005 if side == "buy" else 0.9995)
        capacity = int((item.amount_cny * 0.05 / item.open_price) // 100) * 100
        state = item.buy_state if side == "buy" else item.sell_state
        result[item.instrument_id] = ShadowQuote(
            item.instrument_id,
            open_at,
            price,
            capacity,
            buy_state=state,
            sell_state=state,
        )
    return result


def mark_shadow_session(
    state: ContinuousShadowState,
    observations: tuple[ShadowMarketObservation, ...],
    trading_date: date,
) -> tuple[ContinuousShadowState, tuple[str, ...]]:
    recorded_at = max(item.available_at for item in observations)
    closes = {
        item.instrument_id: item.close_price
        for item in observations
        if item.close_price is not None
    }
    missing = sorted(
        item.instrument_id for item in state.positions if item.instrument_id not in closes
    )
    if missing:
        return state, tuple(f"missing_close_valuation:{item}" for item in missing)
    valued = mark_shadow_to_market(
        state,
        closes,
        trading_date=trading_date,
        as_of=recorded_at,
    )
    return valued, ()


def shadow_fill_blockers(fills: tuple[ShadowFill, ...]) -> tuple[str, ...]:
    return tuple(sorted({item.reason for item in fills if item.status != "filled"}))


def build_shadow_cycle_checkpoint(
    *,
    cycle: ContinuousShadowCycle,
    observations: tuple[ShadowMarketObservation, ...],
    trading_date: date,
    phase: Literal["entry", "valuation", "exit"],
    status: ShadowCycleStatus,
    state: ContinuousShadowState,
    sessions: int,
    entry_order_plan_id: str,
    exit_order_plan_id: str | None,
    event_count: int,
    blocker_codes: tuple[str, ...],
) -> ShadowCycleCheckpoint:
    evidence_hash = canonical_hash(
        [
            item.model_dump(mode="json")
            for item in sorted(observations, key=lambda x: x.instrument_id)
        ]
    )
    recorded_at = max(item.available_at for item in observations)
    identity = {
        "cycle_id": cycle.cycle_id,
        "data_snapshot_id": observations[0].data_snapshot_id,
        "trading_date": trading_date,
        "phase": phase,
        "status": status,
        "state_id": state.state_id,
        "sessions_elapsed": sessions,
        "entry_order_plan_id": entry_order_plan_id,
        "exit_order_plan_id": exit_order_plan_id,
        "event_count": event_count,
        "market_evidence_hash": evidence_hash,
        "blocker_codes": blocker_codes,
        "recorded_at": recorded_at,
    }
    digest = canonical_hash(identity)
    return ShadowCycleCheckpoint.model_validate(
        {
            "checkpoint_id": "shadow-cycle-checkpoint:" + digest.removeprefix("sha256:"),
            "content_hash": digest,
            **identity,
        }
    )


def maximum_drawdown(equities: list[float]) -> float:
    peak = equities[0]
    maximum = 0.0
    for equity in equities:
        peak = max(peak, equity)
        maximum = max(maximum, (peak - equity) / peak)
    return round(maximum, 10)


__all__ = [
    "build_shadow_cycle_checkpoint",
    "mark_shadow_session",
    "maximum_drawdown",
    "shadow_fill_blockers",
    "shadow_quotes",
]
