"""Strict normalized observations for the first production market snapshot."""

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


class ObservationSource(ContractModel):
    provider: Identifier
    source_endpoint: Identifier
    retrieved_at: AwareDatetime
    available_at: AwareDatetime
    schema_version: Version
    source_record_hash: ContentHash


class SecurityMasterObservation(ObservationSource):
    instrument_id: Identifier
    symbol: Identifier
    name: Identifier
    area: str | None = None
    industry: str | None = None
    market: str | None = None
    exchange: Identifier
    currency: Identifier
    list_status: Literal["L", "D", "P"]
    list_date: date | None = None
    delist_date: date | None = None
    connect_flag: str | None = None


class TradeCalendarObservation(ObservationSource):
    exchange: Identifier
    calendar_date: date
    is_open: bool
    previous_trade_date: date | None = None


class DailyBarObservation(ObservationSource):
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
    amount_thousand_cny: float


class AdjustmentFactorObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    adjustment_factor: float


class DailyBasicObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    close: float
    turnover_rate: float | None = None
    turnover_rate_free_float: float | None = None
    volume_ratio: float | None = None
    price_earnings: float | None = None
    price_earnings_ttm: float | None = None
    price_book: float | None = None
    price_sales: float | None = None
    price_sales_ttm: float | None = None
    dividend_yield: float | None = None
    dividend_yield_ttm: float | None = None
    total_shares_ten_thousand: float | None = None
    float_shares_ten_thousand: float | None = None
    free_float_shares_ten_thousand: float | None = None
    total_market_value_ten_thousand_cny: float | None = None
    circulating_market_value_ten_thousand_cny: float | None = None


class PriceLimitObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    previous_close: float | None = None
    upper_limit: float
    lower_limit: float
    limit_prices_usable: bool


class SuspensionEventObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    suspension_timing: str | None = None
    suspension_type: Literal["S", "R"]


HistoricalRiskStatus = Literal["normal", "st", "star_st", "pt", "high_risk"]


class SecurityNameHistoryObservation(ObservationSource):
    instrument_id: Identifier
    name: str
    effective_start_date: date
    effective_end_date: date | None = None
    provider_end_date: date | None = None
    announced_on: date
    change_reason: str
    risk_status: HistoricalRiskStatus
    is_special_treatment: bool


class DailyTradabilityObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    historical_name: str | None = None
    risk_status: HistoricalRiskStatus | Literal["unknown"]
    is_special_treatment: bool | None = None
    research_eligibility: Literal["eligible", "excluded_special_treatment", "unknown_name_status"]
    has_daily_bar: bool
    suspension_state: Literal[
        "no_event",
        "event_with_bar",
        "suspended",
        "ambiguous_event",
        "unknown_no_bar",
    ]
    price_limit_state: Literal["usable", "unusable", "missing"]
    upper_limit_locked: bool | None = None
    lower_limit_locked: bool | None = None
    buy_state: Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"]
    sell_state: Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"]


class CorporateActionObservation(ObservationSource):
    instrument_id: Identifier
    reporting_period: date
    announced_on: date | None = None
    availability_known: bool
    process_status: str
    action_kind: Literal["cash", "stock", "cash_and_stock", "unspecified"]
    stock_dividend_per_share: float | None = None
    cash_dividend_pre_tax_per_share: float | None = None
    cash_dividend_after_tax_per_share: float | None = None
    record_date: date | None = None
    ex_date: date | None = None
    payment_date: date | None = None
    base_date: date | None = None
    base_shares_ten_thousand: float | None = None
    provider_record_hash: ContentHash
    is_implemented: bool


class AdjustedMarketObservation(ObservationSource):
    instrument_id: Identifier
    trade_date: date
    raw_open: float
    raw_high: float
    raw_low: float
    raw_close: float
    adjustment_factor: float
    terminal_adjustment_factor: float
    terminal_factor_date: date
    forward_adjusted_open: float
    forward_adjusted_high: float
    forward_adjusted_low: float
    forward_adjusted_close: float
    backward_adjusted_open: float
    backward_adjusted_high: float
    backward_adjusted_low: float
    backward_adjusted_close: float
    research_open_index: float
    research_high_index: float
    research_low_index: float
    research_close_index: float
    reported_total_return: float
    factor_implied_return: float | None = None
    factor_return_error_bps: float | None = None
    factor_changed: bool
    has_implemented_action_evidence: bool


__all__ = [
    "AdjustedMarketObservation",
    "AdjustmentFactorObservation",
    "CorporateActionObservation",
    "DailyBarObservation",
    "DailyBasicObservation",
    "DailyTradabilityObservation",
    "HistoricalRiskStatus",
    "ObservationSource",
    "PriceLimitObservation",
    "SecurityMasterObservation",
    "SecurityNameHistoryObservation",
    "SuspensionEventObservation",
    "TradeCalendarObservation",
]
