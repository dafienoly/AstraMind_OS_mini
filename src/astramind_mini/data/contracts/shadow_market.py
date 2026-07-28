"""Snapshot-bound daily observations used by local Shadow replay."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import AwareDatetime, ContractModel, Identifier


class ShadowMarketObservation(ContractModel):
    data_snapshot_id: Identifier
    instrument_id: Identifier
    trade_date: date
    available_at: AwareDatetime
    open_price: float | None = Field(default=None, gt=0)
    close_price: float | None = Field(default=None, gt=0)
    amount_cny: float = Field(ge=0)
    buy_state: Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"]
    sell_state: Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"]
    has_daily_bar: bool


__all__ = ["ShadowMarketObservation"]
