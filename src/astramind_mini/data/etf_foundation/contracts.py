"""ETF data-foundation contracts owned by the Data context."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import ContractModel, Identifier, Version
from astramind_mini.data.contracts.observations import ObservationSource


class EtfMasterObservation(ObservationSource):
    instrument_id: Identifier
    name: str
    fund_type: str | None = None
    invest_type: str | None = None
    benchmark: str | None = None
    exchange: Literal["SSE", "SZSE"]
    found_date: date | None = None
    list_date: date
    delist_date: date | None = None
    list_status: Literal["L", "D"]


class EtfDailyObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    previous_close: float
    change: float
    percent_change: float
    volume_lots: float
    amount_cny: float


class EtfShareObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    fund_share: float


class EtfIndustryMappingObservation(ObservationSource):
    taxonomy: Literal["SW"]
    taxonomy_version: Version
    industry_code: Identifier
    industry_name: str
    etf_code: Identifier | None = None
    semantic_tier: Literal[
        "exact",
        "subindustry",
        "composite_proxy",
        "theme_context",
        "unavailable",
    ]
    tracked_index: str | None = None
    eligible_for_foundation: bool
    effective_from: date
    effective_to: date | None = None
    mapping_version: Version
    evidence_source: str


class EtfFoundationQualification(ContractModel):
    data_snapshot_id: Identifier
    evidence_cutoff: date
    mapping_version: Version
    industry_code: Identifier
    industry_name: str
    etf_code: Identifier | None = None
    state: Literal[
        "foundation_eligible",
        "context_only",
        "insufficient_history",
        "insufficient_liquidity",
        "insufficient_size",
        "stale",
        "unavailable",
    ]
    completed_session_count: int
    median_amount_20d_cny: float | None = None
    latest_size_cny: float | None = None
    strategy_gate_ready: Literal[False] = False
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "EtfDailyObservation",
    "EtfFoundationQualification",
    "EtfIndustryMappingObservation",
    "EtfMasterObservation",
    "EtfShareObservation",
]
