"""Contracts for coalesced realtime market projections and minute bars."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class RealtimeIndexQuote(ContractModel):
    instrument_id: Identifier
    last_price: float = Field(ge=0)
    change_percent: float | None = None
    market_time_ms: int | None = Field(default=None, ge=0)


class RealtimeIndustryHeat(ContractModel):
    industry_code: Identifier
    change_percent: float
    observed_constituents: int = Field(ge=0)


class RealtimeMarketProjection(ContractModel):
    projection_id: ContentHash
    provider: Identifier
    session_id: ContentHash
    state: Literal["current", "stale", "disconnected"]
    as_of: AwareDatetime
    latest_received_at: AwareDatetime | None = None
    latest_market_time_ms: int | None = Field(default=None, ge=0)
    granularity_ms: int = Field(ge=250)
    quote_count: int = Field(ge=0)
    breadth_observed: int = Field(default=0, ge=0)
    breadth_expected: int | None = Field(default=None, ge=1)
    breadth_coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    advancing: int = Field(ge=0)
    declining: int = Field(ge=0)
    unchanged: int = Field(ge=0)
    total_amount: float = Field(ge=0)
    indexes: tuple[RealtimeIndexQuote, ...] = ()
    industries: tuple[RealtimeIndustryHeat, ...] = ()
    known_gaps: tuple[str, ...] = ()


class RealtimeMinuteBar(ContractModel):
    provider: Identifier
    session_id: ContentHash
    instrument_id: Identifier
    minute: datetime
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: float = Field(ge=0)
    amount: float = Field(ge=0)
    observation_count: int = Field(ge=1)


class RealtimeBookLevel(ContractModel):
    level: int = Field(ge=1, le=5)
    price: float | None = Field(default=None, ge=0)
    volume: float | None = Field(default=None, ge=0)


class RealtimeInstrumentQuote(ContractModel):
    instrument_id: Identifier
    instrument_name: str | None = None
    instrument_type: Literal["stock", "etf", "index", "other"] = "other"
    industry_code: Identifier | None = None
    market_time_ms: int | None = Field(default=None, ge=0)
    received_at: AwareDatetime
    last_price: float | None = Field(default=None, ge=0)
    previous_close: float | None = Field(default=None, ge=0)
    change_percent: float | None = None
    open_price: float | None = Field(default=None, ge=0)
    high_price: float | None = Field(default=None, ge=0)
    low_price: float | None = Field(default=None, ge=0)
    volume: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)
    upper_limit: float | None = Field(default=None, ge=0)
    lower_limit: float | None = Field(default=None, ge=0)
    stock_status: int | None = None
    status_label: str
    bids: tuple[RealtimeBookLevel, ...] = ()
    asks: tuple[RealtimeBookLevel, ...] = ()


class RealtimeInstrumentProjection(ContractModel):
    projection_id: ContentHash
    provider: Identifier
    session_id: ContentHash
    state: Literal["current", "stale", "disconnected"]
    as_of: AwareDatetime
    market_date: date
    quotes: tuple[RealtimeInstrumentQuote, ...] = ()
    open_minutes: tuple[RealtimeMinuteBar, ...] = ()
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "RealtimeBookLevel",
    "RealtimeIndexQuote",
    "RealtimeIndustryHeat",
    "RealtimeInstrumentProjection",
    "RealtimeInstrumentQuote",
    "RealtimeMarketProjection",
    "RealtimeMinuteBar",
]
