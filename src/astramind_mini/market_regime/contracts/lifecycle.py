"""Read-only contracts for the industry lifecycle structure map."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts.base import ContentHash, ContractModel, Identifier, Version

LifecycleStage = Literal[
    "明显退潮",
    "退潮观察",
    "强势扩散",
    "低位修复",
    "极端低位",
    "方向未明",
]
LifecycleConfidence = Literal["high", "medium", "low"]


class LifecycleTrajectoryPoint(ContractModel):
    trade_date: date
    strong_participation: float
    low_participation: float


class IndustryLifecyclePoint(ContractModel):
    industry_code: Identifier
    industry_name: str
    stage: LifecycleStage
    confidence: LifecycleConfidence
    strong_participation: float | None = None
    low_participation: float | None = None
    strong_change_5d: float | None = None
    low_change_5d: float | None = None
    strong_peak_20d: float | None = None
    strong_drawdown_20d: float | None = None
    amount_share_20d: float | None = None
    eligible_member_count: int
    valid_member_count: int
    coverage_ratio: float
    recently_transitioned: bool = False
    trajectory: tuple[LifecycleTrajectoryPoint, ...] = ()
    known_gaps: tuple[str, ...] = ()


class IndustryLifecycleProjection(ContractModel):
    status: Literal["ready", "stale", "blocked"]
    data_snapshot_id: Identifier
    as_of: datetime
    evidence_cutoff: date | None = None
    taxonomy_version: Version | None = None
    method_version: Version
    industries: tuple[IndustryLifecyclePoint, ...] = ()
    known_gaps: tuple[str, ...] = ()


class IndustryLifecycleIntradayPoint(ContractModel):
    industry_code: Identifier
    strong_participation: float
    low_participation: float
    valid_member_count: int
    coverage_ratio: float


class IndustryLifecycleIntradayProjection(ContractModel):
    provider: Identifier
    session_id: ContentHash
    state: Literal["current", "stale", "disconnected", "blocked"]
    as_of: datetime
    anchor_date: date
    method_version: Version = "lifecycle-intraday-overlay-v1.0.0"
    points: tuple[IndustryLifecycleIntradayPoint, ...] = ()
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "IndustryLifecycleIntradayPoint",
    "IndustryLifecycleIntradayProjection",
    "IndustryLifecyclePoint",
    "IndustryLifecycleProjection",
    "LifecycleConfidence",
    "LifecycleStage",
    "LifecycleTrajectoryPoint",
]
