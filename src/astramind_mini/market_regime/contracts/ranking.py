"""Read-only contracts for industry-internal stock research ranking."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier, Version

from .hierarchy import PriceCandle

ResearchLabel = Literal["优先研究", "积极关注", "中性观察", "数据不足"]


class IndustryResearchRow(ContractModel):
    instrument_id: Identifier
    instrument_name: str
    membership_effective_as_of: date
    overall_priority: float | None = None
    event_sentiment_score: float | None = None
    technical_volume_score: float | None = None
    fundamental_score: float | None = None
    risk_score: float | None = None
    reversal_repair_score: float | None = None
    coverage: float
    research_label: ResearchLabel
    evidence_cutoff: date
    known_gaps: tuple[str, ...] = ()


class IndustryResearchRankingSnapshot(ContractModel):
    status: Literal["ready", "stale", "blocked"]
    ranking_snapshot_id: Identifier
    data_snapshot_id: Identifier
    lifecycle_snapshot_id: Identifier
    as_of: datetime
    evidence_cutoff: date
    taxonomy: Literal["SW"]
    taxonomy_version: Version
    industry_code: Identifier
    industry_name: str
    lifecycle_stage: str
    scoring_definition_version: Version
    member_count: int
    covered_member_count: int
    content_hash: ContentHash
    rows: tuple[IndustryResearchRow, ...] = ()
    selected_instrument_id: Identifier | None = None
    candles: tuple[PriceCandle, ...] = ()
    weekly_candles: tuple[PriceCandle, ...] = ()
    monthly_candles: tuple[PriceCandle, ...] = ()
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "IndustryResearchRankingSnapshot",
    "IndustryResearchRow",
    "ResearchLabel",
]
