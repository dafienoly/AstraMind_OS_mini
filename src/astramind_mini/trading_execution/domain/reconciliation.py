"""Deterministic local-to-broker reconciliation without broker side effects."""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from enum import Enum
from typing import Any

from ..contracts.account import (
    AccountPosition,
    AccountSnapshot,
    CashDifference,
    LocalAccountProjection,
    PositionDifference,
    ReconciliationReport,
)


def canonical_hash(value: object) -> str:
    payload = json.dumps(
        _json_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def synthetic_shadow_projection(
    *,
    as_of: datetime,
    cash_cny: float = 50_000,
    positions: tuple[AccountPosition, ...] = (),
    open_order_fingerprints: tuple[str, ...] = (),
) -> LocalAccountProjection:
    identity = {
        "as_of": as_of,
        "cash_cny": cash_cny,
        "positions": sorted(
            (position.model_dump(mode="json") for position in positions),
            key=lambda item: str(item["instrument_id"]),
        ),
        "open_order_fingerprints": sorted(open_order_fingerprints),
        "source": "synthetic_shadow_ledger",
    }
    digest = canonical_hash(identity)
    return LocalAccountProjection(
        projection_id="local-account-projection:" + digest.removeprefix("sha256:"),
        as_of=as_of,
        cash_cny=cash_cny,
        positions=tuple(sorted(positions, key=lambda item: item.instrument_id)),
        open_order_fingerprints=tuple(sorted(open_order_fingerprints)),
        source="synthetic_shadow_ledger",
        content_hash=digest,
    )


def reconcile_account(
    local: LocalAccountProjection,
    broker: AccountSnapshot,
    *,
    created_at: datetime,
    cash_tolerance_cny: float = 0.01,
) -> ReconciliationReport:
    cash_delta = round(broker.cash.cash_cny - local.cash_cny, 6)
    cash_difference = (
        CashDifference(
            local_cash_cny=local.cash_cny,
            broker_cash_cny=broker.cash.cash_cny,
            delta_cny=cash_delta,
        )
        if abs(cash_delta) > cash_tolerance_cny
        else None
    )
    local_positions = {item.instrument_id: item.quantity for item in local.positions}
    broker_positions = {item.instrument_id: item.quantity for item in broker.positions}
    position_differences = tuple(
        PositionDifference(
            instrument_id=instrument_id,
            local_quantity=local_positions.get(instrument_id, 0),
            broker_quantity=broker_positions.get(instrument_id, 0),
            delta_quantity=broker_positions.get(instrument_id, 0)
            - local_positions.get(instrument_id, 0),
        )
        for instrument_id in sorted(set(local_positions) | set(broker_positions))
        if local_positions.get(instrument_id, 0) != broker_positions.get(instrument_id, 0)
    )
    broker_open = {item.order_fingerprint for item in broker.orders if item.is_open}
    local_open = set(local.open_order_fingerprints)
    unexpected = tuple(sorted(broker_open - local_open))
    missing = tuple(sorted(local_open - broker_open))
    blockers = []
    if cash_difference is not None:
        blockers.append("cash_difference")
    if position_differences:
        blockers.append("position_difference")
    if unexpected:
        blockers.append("unexpected_broker_open_order")
    if missing:
        blockers.append("missing_broker_open_order")
    identity = {
        "local_projection_id": local.projection_id,
        "account_snapshot_id": broker.account_snapshot_id,
        "account_mode": broker.account_mode,
        "cash_difference": (cash_difference.model_dump(mode="json") if cash_difference else None),
        "position_differences": [item.model_dump(mode="json") for item in position_differences],
        "unexpected_open_order_fingerprints": unexpected,
        "missing_open_order_fingerprints": missing,
        "blocker_codes": blockers,
        "created_at": created_at,
    }
    digest = canonical_hash(identity)
    return ReconciliationReport(
        reconciliation_report_id="reconciliation-report:" + digest.removeprefix("sha256:"),
        local_projection_id=local.projection_id,
        account_snapshot_id=broker.account_snapshot_id,
        account_mode=broker.account_mode,
        status="blocked" if blockers else "matched",
        cash_difference=cash_difference,
        position_differences=position_differences,
        unexpected_open_order_fingerprints=unexpected,
        missing_open_order_fingerprints=missing,
        blocker_codes=tuple(blockers),
        created_at=created_at,
        content_hash=digest,
    )


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return _json_value(value.model_dump(mode="json"))
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


__all__ = ["canonical_hash", "reconcile_account", "synthetic_shadow_projection"]
