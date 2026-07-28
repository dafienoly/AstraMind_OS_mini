"""Strict read-only account and reconciliation contracts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

AccountMode = Literal["simulation", "live"]
ReconciliationStatus = Literal["matched", "blocked"]


class AccountCash(ContractModel):
    cash_cny: float = Field(ge=0)
    frozen_cash_cny: float = Field(ge=0)
    market_value_cny: float = Field(ge=0)
    total_asset_cny: float = Field(ge=0)


class AccountPosition(ContractModel):
    instrument_id: Identifier
    quantity: int = Field(ge=0)
    available_quantity: int = Field(ge=0)
    frozen_quantity: int = Field(ge=0)
    average_price: float | None = Field(default=None, ge=0)
    market_value_cny: float = Field(ge=0)

    @model_validator(mode="after")
    def validate_quantities(self) -> AccountPosition:
        if self.available_quantity > self.quantity or self.frozen_quantity > self.quantity:
            raise ValueError("账户持仓可用或冻结数量超过总数量")
        return self


class AccountOrder(ContractModel):
    order_fingerprint: ContentHash
    instrument_id: Identifier
    side: Literal["buy", "sell", "unknown"]
    status: str
    quantity: int = Field(ge=0)
    filled_quantity: int = Field(ge=0)
    price: float | None = Field(default=None, ge=0)
    occurred_at: AwareDatetime | None = None
    is_open: bool

    @model_validator(mode="after")
    def validate_fill(self) -> AccountOrder:
        if self.filled_quantity > self.quantity:
            raise ValueError("账户委托成交数量超过委托数量")
        return self


class AccountTrade(ContractModel):
    trade_fingerprint: ContentHash
    order_fingerprint: ContentHash
    instrument_id: Identifier
    side: Literal["buy", "sell", "unknown"]
    quantity: int = Field(ge=0)
    price: float = Field(ge=0)
    amount_cny: float = Field(ge=0)
    occurred_at: AwareDatetime | None = None


class AccountSnapshot(ContractModel):
    account_snapshot_id: Identifier
    provider: Literal["miniqmt"]
    account_mode: AccountMode
    account_fingerprint: ContentHash
    as_of: AwareDatetime
    trading_date: date
    cash: AccountCash
    positions: tuple[AccountPosition, ...]
    orders: tuple[AccountOrder, ...]
    trades: tuple[AccountTrade, ...]
    client_version: Version
    gateway_version: Version
    content_hash: ContentHash
    known_gaps: tuple[str, ...] = ()


class LocalAccountProjection(ContractModel):
    projection_id: Identifier
    as_of: AwareDatetime
    cash_cny: float = Field(ge=0)
    positions: tuple[AccountPosition, ...] = ()
    open_order_fingerprints: tuple[ContentHash, ...] = ()
    source: Literal["synthetic_shadow_ledger"]
    content_hash: ContentHash


class CashDifference(ContractModel):
    local_cash_cny: float = Field(ge=0)
    broker_cash_cny: float = Field(ge=0)
    delta_cny: float


class PositionDifference(ContractModel):
    instrument_id: Identifier
    local_quantity: int = Field(ge=0)
    broker_quantity: int = Field(ge=0)
    delta_quantity: int


class ReconciliationReport(ContractModel):
    reconciliation_report_id: Identifier
    local_projection_id: Identifier
    account_snapshot_id: Identifier
    account_mode: AccountMode
    status: ReconciliationStatus
    cash_difference: CashDifference | None
    position_differences: tuple[PositionDifference, ...]
    unexpected_open_order_fingerprints: tuple[ContentHash, ...]
    missing_open_order_fingerprints: tuple[ContentHash, ...]
    blocker_codes: tuple[str, ...]
    broker_actions_allowed: Literal[False] = False
    created_at: AwareDatetime
    content_hash: ContentHash


__all__ = [
    "AccountCash",
    "AccountMode",
    "AccountOrder",
    "AccountPosition",
    "AccountSnapshot",
    "AccountTrade",
    "CashDifference",
    "LocalAccountProjection",
    "PositionDifference",
    "ReconciliationReport",
    "ReconciliationStatus",
]
