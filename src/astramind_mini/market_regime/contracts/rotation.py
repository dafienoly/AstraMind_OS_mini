"""Strict contracts for versioned industry relative-rotation evidence."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

Quadrant = Literal["leading", "weakening", "lagging", "improving"]


class RotationFormula(ContractModel):
    formula_version: Version
    benchmark_id: Identifier
    benchmark_definition_version: Version
    taxonomy: Literal["SW"]
    taxonomy_version: Literal["SW2021"]
    fast_window: int
    slow_window: int
    momentum_window: int
    warmup_sessions: int
    output_sessions: int
    scale: float
    clip_z: float
    neutral_band: float
    confirmation_sessions: int
    required_industry_coverage: float
    minimum_constituent_count: int
    rounding_decimals: int


class RotationPoint(ContractModel):
    industry_code: Identifier
    industry_name: str
    trade_date: date
    relative_trend: float
    relative_momentum: float
    quadrant: Quadrant
    coverage: float
    constituent_count: int
    direction_x: float
    direction_y: float
    overflow: bool


class RotationEvent(ContractModel):
    industry_code: Identifier
    industry_name: str
    from_quadrant: Quadrant
    to_quadrant: Quadrant
    first_cross_date: date
    confirmed_date: date
    formula_version: Version


class MarketRotationSnapshot(ContractModel):
    rotation_snapshot_id: Identifier
    data_snapshot_id: Identifier
    as_of: AwareDatetime
    benchmark_id: Identifier
    benchmark_definition_version: Version
    formula: RotationFormula
    taxonomy: Literal["SW"]
    taxonomy_version: Literal["SW2021"]
    industry_count: int
    covered_industry_count: int
    coverage_rule: str
    date_range: tuple[date, date]
    dates: tuple[date, ...]
    points: tuple[RotationPoint, ...]
    events: tuple[RotationEvent, ...]
    created_at: AwareDatetime
    content_hash: ContentHash
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "MarketRotationSnapshot",
    "Quadrant",
    "RotationEvent",
    "RotationFormula",
    "RotationPoint",
]
