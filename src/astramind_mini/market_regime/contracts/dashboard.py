"""Page query contracts for the broad-market and industry-heat views."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts.base import ContractModel, Identifier, Version

from .hierarchy import PriceCandle


class MarketBreadth(ContractModel):
    advancing: int
    declining: int
    unchanged: int
    advance_ratio: float
    new_high_250d: int
    new_low_250d: int
    upper_limit_locked: int
    lower_limit_locked: int


class MarketLiquidity(ContractModel):
    amount_cny: float
    amount_change_20d: float | None = None
    amount_percentile_250d: float | None = None


class MarketRegimeEvidence(ContractModel):
    state: Literal["strong", "balanced", "weak", "divergent", "unknown"]
    label: str
    confidence: float
    definition_version: Version
    observations: tuple[str, ...] = ()


class BroadIndexView(ContractModel):
    instrument_id: Identifier
    instrument_name: str
    latest_trade_date: date
    latest_close: float
    change: float
    percent_change: float
    return_20d: float | None = None
    drawdown_250d: float | None = None
    candles: tuple[PriceCandle, ...]


class IndustryHeatRow(ContractModel):
    industry_code: Identifier
    industry_name: str
    trade_date: date
    percent_change: float
    relative_strength: float
    breadth_ratio: float | None = None
    advancing: int
    declining: int
    member_count: int
    covered_member_count: int
    coverage_ratio: float
    amount_change_20d: float | None = None
    volatility_20d: float | None = None
    price_earnings: float | None = None
    price_book: float | None = None
    leading_instrument_id: Identifier | None = None
    leading_instrument_name: str | None = None
    leading_percent_change: float | None = None
    known_gaps: tuple[str, ...] = ()


class MarketDashboardProjection(ContractModel):
    status: Literal["ready", "stale", "blocked"]
    data_snapshot_id: Identifier
    as_of: datetime
    evidence_cutoff: date | None = None
    projection_version: Version
    selected_index_id: Identifier | None = None
    indexes: tuple[BroadIndexView, ...] = ()
    breadth: MarketBreadth | None = None
    liquidity: MarketLiquidity | None = None
    regime: MarketRegimeEvidence | None = None
    industries: tuple[IndustryHeatRow, ...] = ()
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "BroadIndexView",
    "IndustryHeatRow",
    "MarketBreadth",
    "MarketDashboardProjection",
    "MarketLiquidity",
    "MarketRegimeEvidence",
]
