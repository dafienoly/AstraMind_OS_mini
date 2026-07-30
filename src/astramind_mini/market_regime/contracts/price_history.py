"""Bounded, snapshot-pinned price-history response contracts."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

from .hierarchy import PriceCandle

InstrumentType = Literal["stock", "index", "etf"]
HistoryWindow = Literal["one_year", "five_years", "listed_since"]
CoverageBasis = Literal[
    "listing_date_or_earliest_reliable_record",
    "official_launch_or_earliest_reliable_record",
]


class PriceHistoryPage(ContractModel):
    instrument_type: InstrumentType
    instrument_id: Identifier
    instrument_name: str
    data_snapshot_id: Identifier
    dataset_name: Identifier
    dataset_version: ContentHash
    dataset_content_hash: ContentHash
    evidence_cutoff: date
    window: HistoryWindow
    requested_start: date
    requested_end: date
    coverage_start: date | None = None
    coverage_end: date | None = None
    coverage_basis: CoverageBasis
    listing_date: date | None = None
    schema_version: Version
    bars: tuple[PriceCandle, ...] = ()
    page_size: int
    has_more: bool
    next_cursor: date | None = None
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "CoverageBasis",
    "HistoryWindow",
    "InstrumentType",
    "PriceHistoryPage",
]
