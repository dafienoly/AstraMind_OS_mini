"""Normalize sanitized MiniQMT query payloads into strict account evidence."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from ..contracts.account import (
    AccountCash,
    AccountMode,
    AccountOrder,
    AccountPosition,
    AccountSnapshot,
    AccountTrade,
)
from ..domain.reconciliation import canonical_hash


class AccountNormalizationError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def build_account_snapshot(
    *,
    account_mode: AccountMode,
    account_fingerprint: str,
    as_of: datetime,
    asset: dict[str, object],
    positions: list[object],
    orders: list[object],
    trades: list[object],
    client_version: str,
    gateway_version: str,
    known_gaps: tuple[str, ...] = ("non_atomic_sequential_account_queries",),
) -> AccountSnapshot:
    normalized_positions = tuple(
        sorted(
            (AccountPosition.model_validate(item, strict=True) for item in positions),
            key=lambda item: item.instrument_id,
        )
    )
    normalized_orders = tuple(
        sorted((_order(item) for item in orders), key=lambda item: item.order_fingerprint)
    )
    normalized_trades = tuple(
        sorted((_trade(item) for item in trades), key=lambda item: item.trade_fingerprint)
    )
    _require_unique(
        (item.instrument_id for item in normalized_positions),
        "duplicate_position",
    )
    _require_unique(
        (item.order_fingerprint for item in normalized_orders),
        "duplicate_order",
    )
    _require_unique(
        (item.trade_fingerprint for item in normalized_trades),
        "duplicate_trade",
    )
    trading_date = as_of.astimezone(ZoneInfo("Asia/Shanghai")).date()
    identity = {
        "provider": "miniqmt",
        "account_mode": account_mode,
        "account_fingerprint": account_fingerprint,
        "as_of": as_of,
        "trading_date": trading_date,
        "cash": asset,
        "positions": [item.model_dump(mode="json") for item in normalized_positions],
        "orders": [item.model_dump(mode="json") for item in normalized_orders],
        "trades": [item.model_dump(mode="json") for item in normalized_trades],
        "client_version": client_version,
        "gateway_version": gateway_version,
        "known_gaps": list(known_gaps),
    }
    digest = canonical_hash(identity)
    return AccountSnapshot(
        account_snapshot_id="account-snapshot:" + digest.removeprefix("sha256:"),
        provider="miniqmt",
        account_mode=account_mode,
        account_fingerprint=account_fingerprint,
        as_of=as_of,
        trading_date=trading_date,
        cash=AccountCash.model_validate(asset, strict=True),
        positions=normalized_positions,
        orders=normalized_orders,
        trades=normalized_trades,
        client_version=client_version,
        gateway_version=gateway_version,
        content_hash=digest,
        known_gaps=known_gaps,
    )


def _order(value: object) -> AccountOrder:
    if not isinstance(value, dict):
        raise AccountNormalizationError("invalid_order")
    return AccountOrder.model_validate(
        {**value, "occurred_at": _timestamp(value.get("occurred_at"))},
        strict=True,
    )


def _trade(value: object) -> AccountTrade:
    if not isinstance(value, dict):
        raise AccountNormalizationError("invalid_trade")
    return AccountTrade.model_validate(
        {**value, "occurred_at": _timestamp(value.get("occurred_at"))},
        strict=True,
    )


def _timestamp(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if not isinstance(value, str | int | float):
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 10_000_000_000:
        number /= 1000
    return datetime.fromtimestamp(number, tz=UTC)


def _require_unique(values: Iterable[str], code: str) -> None:
    sequence = tuple(values)
    if len(sequence) != len(set(sequence)):
        raise AccountNormalizationError(code)


__all__ = ["AccountNormalizationError", "build_account_snapshot"]
