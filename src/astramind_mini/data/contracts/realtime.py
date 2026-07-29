"""Strict contracts for MiniQMT L1 sessions and immutable microbatches."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import Field

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)


class FeedSessionState(StrEnum):
    COMPLETE = "complete"
    EMPTY = "empty"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class RealtimeQuoteObservation(ContractModel):
    instrument_id: Identifier
    market_time_ms: int | None = Field(default=None, ge=0)
    received_at: AwareDatetime
    last_price: float | None = Field(default=None, ge=0)
    previous_close: float | None = Field(default=None, ge=0)
    open_price: float | None = Field(default=None, ge=0)
    high_price: float | None = Field(default=None, ge=0)
    low_price: float | None = Field(default=None, ge=0)
    volume: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)
    bid_prices: tuple[float, ...] = ()
    ask_prices: tuple[float, ...] = ()
    bid_volumes: tuple[float, ...] = ()
    ask_volumes: tuple[float, ...] = ()
    stock_status: int | None = None
    open_interest: float | None = Field(default=None, ge=0)
    raw_content_hash: ContentHash


class QuoteMicroBatch(ContractModel):
    microbatch_id: ContentHash
    session_id: ContentHash
    provider: Identifier
    sequence: int = Field(ge=0)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    schema_version: Version
    row_count: int = Field(ge=0)
    raw_content_hash: ContentHash
    normalized_content_hash: ContentHash


class FeedSessionReport(ContractModel):
    session_id: ContentHash
    provider: Identifier
    client_version: Version
    state: FeedSessionState
    markets: tuple[str, ...] = Field(min_length=1)
    market_date: date | None = None
    subscribed_at: AwareDatetime
    ended_at: AwareDatetime
    microbatch_ids: tuple[ContentHash, ...]
    received_messages: int = Field(ge=0)
    duplicate_messages: int = Field(ge=0)
    disconnects: int = Field(ge=0)
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "FeedSessionReport",
    "FeedSessionState",
    "QuoteMicroBatch",
    "RealtimeQuoteObservation",
]
