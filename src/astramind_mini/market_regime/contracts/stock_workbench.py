"""Public contracts for the one canonical A-share stock workbench."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)
from astramind_mini.data.public import RealtimeInstrumentQuote, RealtimeMinuteBar

from .hierarchy import PriceCandle, StockEvidence

StockInspectionOrigin = Literal[
    "watchlist",
    "industry_rotation",
    "industry_lifecycle",
    "industry_ranking",
    "strategy_candidate",
    "portfolio_holding",
    "attention_case",
]
StockInspectionMode = Literal[
    "current",
    "completed",
    "historical_replay",
    "sealed_evidence",
]
StockReturnTarget = Literal[
    "market_stocks",
    "industry_rotation",
    "industry_lifecycle",
    "industry_ranking",
    "strategy_arena",
    "portfolio",
    "today",
]


class StockInspectionFocus(ContractModel):
    focus_id: ContentHash
    instrument_id: Identifier
    origin: StockInspectionOrigin
    as_of: date
    data_snapshot_id: Identifier
    industry_code: Identifier | None = None
    cohort_id: Identifier | None = None
    strategy_version_id: Identifier | None = None
    portfolio_snapshot_id: Identifier | None = None
    attention_case_id: Identifier | None = None
    mode: StockInspectionMode
    return_target: StockReturnTarget
    created_at: AwareDatetime


class EvidenceSectionIdentity(ContractModel):
    state: Literal["ready", "unavailable", "blocked"]
    as_of: date
    provider: Identifier
    content_identity: ContentHash
    known_gaps: tuple[str, ...] = ()


class StockInstrumentIdentity(ContractModel):
    instrument_id: Identifier
    instrument_name: str
    exchange: str
    market: str
    risk_status: str | None = None
    is_special_treatment: bool | None = None


class StockIndustryContext(ContractModel):
    evidence: EvidenceSectionIdentity
    taxonomy: Literal["SW"]
    taxonomy_version: str
    l1_code: Identifier | None = None
    l1_name: str | None = None
    l2_code: Identifier | None = None
    l2_name: str | None = None


class CompletedStockMarketEvidence(ContractModel):
    evidence: EvidenceSectionIdentity
    daily: tuple[PriceCandle, ...] = ()
    weekly: tuple[PriceCandle, ...] = ()
    monthly: tuple[PriceCandle, ...] = ()


class StockRealtimeMarketOverlay(ContractModel):
    state: Literal["current", "stale", "disconnected"]
    provider: Identifier
    session_id: ContentHash
    as_of: AwareDatetime
    quote: RealtimeInstrumentQuote
    minutes: tuple[RealtimeMinuteBar, ...] = ()
    known_gaps: tuple[str, ...] = ()


class StockWorkbenchProjection(ContractModel):
    focus: StockInspectionFocus
    instrument_identity: StockInstrumentIdentity
    completed_market_evidence: CompletedStockMarketEvidence
    realtime_market_overlay: StockRealtimeMarketOverlay | None = None
    industry_context: StockIndustryContext
    stock_evidence: StockEvidence
    content_identity: ContentHash
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "CompletedStockMarketEvidence",
    "EvidenceSectionIdentity",
    "StockIndustryContext",
    "StockInspectionFocus",
    "StockInspectionMode",
    "StockInspectionOrigin",
    "StockInstrumentIdentity",
    "StockRealtimeMarketOverlay",
    "StockReturnTarget",
    "StockWorkbenchProjection",
]
