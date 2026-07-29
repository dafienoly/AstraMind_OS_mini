"""Normalized observations for MiniQMT-sourced reference and financial data."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import ContentHash, Identifier

from .observations import ObservationSource


class FinancialFactObservation(ObservationSource):
    instrument_id: Identifier
    statement_type: Identifier
    report_period: date
    announced_on: date
    revision_identity: ContentHash
    field_name: Identifier
    numeric_value: float
    currency: str | None = None
    unit: str
    applicability: Literal["observed", "not_applicable"] = "observed"


class TopHolderObservation(ObservationSource):
    instrument_id: Identifier
    holder_scope: Literal["top10", "top10_float"]
    report_period: date
    announced_on: date
    rank: int | None = None
    holder_name: str
    holding_amount: float | None = None
    holding_ratio_percent: float | None = None
    holder_type: str | None = None
    revision_identity: ContentHash


class IndexConstituentWeightObservation(ObservationSource):
    index_id: Identifier
    instrument_id: Identifier
    observed_on: date
    weight_percent: float
    membership_semantics: Literal["current_snapshot"] = "current_snapshot"


class CurrentSectorMembershipObservation(ObservationSource):
    sector_name: Identifier
    instrument_id: Identifier
    observed_on: date
    membership_semantics: Literal["current_only"] = "current_only"


class InstrumentSnapshotObservation(ObservationSource):
    instrument_id: Identifier
    observed_on: date
    name: str | None = None
    exchange_id: str | None = None
    listed_on: date | None = None
    delisted_on: date | None = None
    total_shares: float | None = None
    float_shares: float | None = None
    previous_close: float | None = None
    upper_limit: float | None = None
    lower_limit: float | None = None
    is_trading: bool | None = None
    stock_status: int | None = None


__all__ = [
    "CurrentSectorMembershipObservation",
    "FinancialFactObservation",
    "IndexConstituentWeightObservation",
    "InstrumentSnapshotObservation",
    "TopHolderObservation",
]
