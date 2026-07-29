"""Strict read-only contracts for the SW2021 hierarchy research view."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts.base import ContractModel, Identifier

from .rotation import MarketRotationSnapshot


class IndustryHierarchyNode(ContractModel):
    code: Identifier
    name: str
    level: Literal["L1", "L2", "stock"]
    parent_code: Identifier | None = None


class PriceCandle(ContractModel):
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume_lots: float
    amount_cny: float | None = None


class StockFundamentalEvidence(ContractModel):
    market_date: date
    available_at: datetime
    latest_close: float
    percent_change: float | None = None
    turnover_rate: float | None = None
    price_earnings_ttm: float | None = None
    price_book: float | None = None
    total_market_value_cny: float | None = None
    circulating_market_value_cny: float | None = None
    amount_cny: float | None = None


class ShareholderConcentrationEvidence(ContractModel):
    status: Literal["ready", "unavailable", "insufficient_history"]
    announced_on: date | None = None
    reporting_period: date | None = None
    available_at: datetime | None = None
    holder_count: int | None = None
    previous_holder_count: int | None = None
    change_rate: float | None = None
    direction: Literal["concentrating", "dispersing", "unchanged"] | None = None
    consecutive_periods: int = 0
    observation_age_days: int | None = None
    known_gaps: tuple[str, ...] = ()


class StockEvidence(ContractModel):
    instrument_id: Identifier
    instrument_name: str
    as_of: date
    fundamental: StockFundamentalEvidence | None = None
    fundamental_history: tuple[StockFundamentalEvidence, ...] = ()
    shareholder_concentration: ShareholderConcentrationEvidence
    shareholder_concentration_history: tuple[ShareholderConcentrationEvidence, ...] = ()
    known_gaps: tuple[str, ...] = ()


class IndustryHierarchyView(ContractModel):
    status: Literal["ready", "blocked"]
    data_snapshot_id: Identifier
    as_of: date
    level: Literal["L1", "L2", "stock"]
    comparison_scope: Literal["l1", "siblings", "all_l2", "members"]
    benchmark_id: Identifier
    parent_code: Identifier | None = None
    selected_code: Identifier | None = None
    nodes: tuple[IndustryHierarchyNode, ...] = ()
    rotation: MarketRotationSnapshot | None = None
    candles: tuple[PriceCandle, ...] = ()
    weekly_candles: tuple[PriceCandle, ...] = ()
    monthly_candles: tuple[PriceCandle, ...] = ()
    stock_evidence: StockEvidence | None = None
    known_gaps: tuple[str, ...] = ()


__all__ = [
    "IndustryHierarchyNode",
    "IndustryHierarchyView",
    "PriceCandle",
    "ShareholderConcentrationEvidence",
    "StockEvidence",
    "StockFundamentalEvidence",
]
