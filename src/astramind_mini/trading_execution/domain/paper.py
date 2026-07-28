"""Pure monotonic state transitions for offline Paper execution."""

from __future__ import annotations

from typing import Any, Literal

from ..contracts.paper import (
    PaperBrokerObservation,
    PaperObservationKind,
    PaperOrderIntent,
    PaperOrderProjection,
    PaperOrderState,
    PaperPreflightDecision,
)
from .reconciliation import canonical_hash

_PREFLIGHT_FIELDS = (
    "account_mode_verified",
    "reconciliation_matched",
    "quote_fresh",
    "trading_window_open",
    "tradable",
    "cash_sufficient",
    "lot_valid",
    "t_plus_one_valid",
    "drawdown_allowed",
    "mandate_approved",
)


def build_paper_preflight(
    *,
    created_at: Any,
    checks: dict[str, bool],
    evidence_kind: Literal["synthetic_offline", "real_miniqmt"] = "synthetic_offline",
    evidence_ids: tuple[str, ...] = (),
) -> PaperPreflightDecision:
    missing = set(_PREFLIGHT_FIELDS) - set(checks)
    extra = set(checks) - set(_PREFLIGHT_FIELDS)
    if missing or extra:
        raise ValueError("Paper 提交前检查字段不完整")
    blockers = tuple(sorted(name for name, passed in checks.items() if not passed))
    payload = {
        "evidence_kind": evidence_kind,
        "evidence_ids": evidence_ids,
        **checks,
        "blocker_codes": blockers,
        "created_at": created_at,
    }
    digest = canonical_hash(payload)
    return PaperPreflightDecision(
        decision_id="paper-preflight:" + digest.removeprefix("sha256:"),
        content_hash=digest,
        **payload,
    )


def build_paper_intent(
    *,
    order_plan: Any,
    line_id: str,
    instrument_id: str,
    side: Literal["buy", "sell"],
    quantity: int,
    limit_price: float,
    preflight: PaperPreflightDecision,
    created_at: Any,
) -> PaperOrderIntent:
    if str(order_plan.execution_mode) != "paper":
        raise ValueError("Paper 意图只接受 execution_mode=paper")
    if preflight.blocker_codes:
        raise ValueError("Paper 提交前检查存在阻断")
    payload = {
        "order_plan_id": order_plan.order_plan_id,
        "line_id": line_id,
        "instrument_id": instrument_id,
        "side": side,
        "quantity": quantity,
        "limit_price": limit_price,
        "preflight_decision_id": preflight.decision_id,
    }
    digest = canonical_hash(payload)
    identity = digest.removeprefix("sha256:")
    return PaperOrderIntent(
        intent_id="paper-intent:" + identity,
        order_plan=order_plan,
        line_id=line_id,
        idempotency_key="astramind-paper-" + identity[:32],
        instrument_id=instrument_id,
        side=side,
        quantity=quantity,
        limit_price=limit_price,
        preflight_decision_id=preflight.decision_id,
        created_at=created_at,
        content_hash=digest,
    )


def initial_paper_projection(intent: PaperOrderIntent) -> PaperOrderProjection:
    return _projection(
        intent,
        state=PaperOrderState.PREPARED,
        filled=0,
        fingerprint=None,
        sequence=None,
        evidence_count=0,
        updated_at=intent.created_at,
    )


def replay_paper_observations(
    intent: PaperOrderIntent,
    observations: tuple[PaperBrokerObservation, ...],
) -> PaperOrderProjection:
    projection = initial_paper_projection(intent)
    evidence_ids: set[str] = set()
    for observation in observations:
        if observation.evidence_id in evidence_ids:
            continue
        evidence_ids.add(observation.evidence_id)
        projection = apply_paper_observation(intent, projection, observation)
    return projection


def apply_paper_observation(
    intent: PaperOrderIntent,
    current: PaperOrderProjection,
    observation: PaperBrokerObservation,
) -> PaperOrderProjection:
    _validate_observation(intent, current, observation)
    if _is_late_sequence(current, observation):
        return _projection(
            intent,
            state=current.state,
            filled=current.cumulative_filled_quantity,
            fingerprint=current.broker_order_fingerprint,
            sequence=current.last_broker_sequence,
            evidence_count=current.evidence_count + 1,
            updated_at=max(current.updated_at, observation.received_at),
        )
    filled = observation.cumulative_filled_quantity
    if filled < current.cumulative_filled_quantity:
        raise ValueError("Paper 累计成交数量不能倒退")
    state = _next_state(current.state, observation.kind, filled, intent.quantity)
    fingerprint = observation.broker_order_fingerprint or current.broker_order_fingerprint
    sequence = observation.broker_sequence
    if sequence is None:
        sequence = current.last_broker_sequence
    return _projection(
        intent,
        state=state,
        filled=filled,
        fingerprint=fingerprint,
        sequence=sequence,
        evidence_count=current.evidence_count + 1,
        updated_at=max(current.updated_at, observation.received_at),
    )


def _validate_observation(
    intent: PaperOrderIntent,
    current: PaperOrderProjection,
    observation: PaperBrokerObservation,
) -> None:
    if observation.intent_id != intent.intent_id or current.intent_id != intent.intent_id:
        raise ValueError("Paper 证据与意图身份不一致")
    if observation.idempotency_key != intent.idempotency_key:
        raise ValueError("Paper 幂等键不一致")
    event = observation.execution_event
    if (
        event.order_plan_id != intent.order_plan.order_plan_id
        or str(event.execution_mode) != "paper"
    ):
        raise ValueError("Paper ExecutionEvent 血缘或模式不一致")
    if observation.cumulative_filled_quantity > intent.quantity:
        raise ValueError("Paper 累计成交数量超过委托数量")


def _is_late_sequence(
    current: PaperOrderProjection,
    observation: PaperBrokerObservation,
) -> bool:
    return (
        current.last_broker_sequence is not None
        and observation.broker_sequence is not None
        and observation.broker_sequence < current.last_broker_sequence
    )


def _next_state(
    state: PaperOrderState,
    kind: PaperObservationKind,
    filled: int,
    requested: int,
) -> PaperOrderState:
    if filled == requested:
        return PaperOrderState.FILLED
    if state == PaperOrderState.FILLED:
        raise ValueError("Paper 已成交终态不能变更")
    if state == PaperOrderState.REJECTED:
        if kind != PaperObservationKind.REJECTED:
            raise ValueError("Paper 已拒绝终态出现矛盾证据")
        return state
    if kind == PaperObservationKind.REJECTED:
        if filled:
            raise ValueError("已有成交的 Paper 委托不能转为拒绝")
        return PaperOrderState.REJECTED
    if kind == PaperObservationKind.CANCELLED:
        return PaperOrderState.CANCELLED
    if state == PaperOrderState.CANCELLED:
        return state
    if kind == PaperObservationKind.CANCEL_REQUESTED:
        return PaperOrderState.CANCEL_PENDING
    if state == PaperOrderState.CANCEL_PENDING:
        return state
    if filled > 0 or kind == PaperObservationKind.PARTIAL_FILL:
        return PaperOrderState.PARTIALLY_FILLED
    if kind == PaperObservationKind.ACKNOWLEDGED:
        return PaperOrderState.ACKNOWLEDGED
    if kind in {
        PaperObservationKind.SUBMISSION_UNKNOWN,
        PaperObservationKind.RECOVERY_NOT_FOUND,
    }:
        return PaperOrderState.SUBMISSION_UNKNOWN
    return state


def _projection(
    intent: PaperOrderIntent,
    *,
    state: PaperOrderState,
    filled: int,
    fingerprint: str | None,
    sequence: int | None,
    evidence_count: int,
    updated_at: Any,
) -> PaperOrderProjection:
    payload = {
        "intent_id": intent.intent_id,
        "idempotency_key": intent.idempotency_key,
        "state": state,
        "requested_quantity": intent.quantity,
        "cumulative_filled_quantity": filled,
        "remaining_quantity": intent.quantity - filled,
        "broker_order_fingerprint": fingerprint,
        "last_broker_sequence": sequence,
        "evidence_count": evidence_count,
        "recovery_required": state == PaperOrderState.SUBMISSION_UNKNOWN,
        "updated_at": updated_at,
    }
    digest = canonical_hash(payload)
    return PaperOrderProjection(
        projection_id="paper-projection:" + digest.removeprefix("sha256:"),
        content_hash=digest,
        **payload,
    )


__all__ = [
    "apply_paper_observation",
    "build_paper_intent",
    "build_paper_preflight",
    "initial_paper_projection",
    "replay_paper_observations",
]
