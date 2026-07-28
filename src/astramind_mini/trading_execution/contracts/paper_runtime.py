"""Strict evidence for the first real MiniQMT Paper canary cycle."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class PaperConvergenceReport(ContractModel):
    report_id: Identifier
    intent_id: Identifier
    starting_account_snapshot_id: Identifier
    ending_account_snapshot_id: Identifier
    projection_id: Identifier
    instrument_id: Identifier
    starting_quantity: int = Field(ge=0)
    ending_quantity: int = Field(ge=0)
    inherited_quantity: int = Field(ge=0)
    managed_quantity: int = Field(ge=0)
    projected_filled_quantity: int = Field(ge=0)
    broker_trade_quantity: int = Field(ge=0)
    starting_cash_cny: float = Field(ge=0)
    ending_cash_cny: float = Field(ge=0)
    broker_trade_amount_cny: float = Field(ge=0)
    open_canary_order_count: int = Field(ge=0)
    status: Literal["converged", "blocked"]
    blocker_codes: tuple[Identifier, ...]
    created_at: AwareDatetime
    content_hash: ContentHash


__all__ = ["PaperConvergenceReport"]
