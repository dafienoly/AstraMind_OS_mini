"""Immutable contracts for the weekly core-research input waist."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts import DataSnapshot
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)


class CoreBoard(StrEnum):
    SSE_MAIN = "sse_main"
    SSE_STAR = "sse_star"
    SZSE_MAIN = "szse_main"
    SZSE_CHINEXT = "szse_chinext"
    BSE = "bse"
    UNKNOWN = "unknown"


class CoreRiskStatus(StrEnum):
    NORMAL = "normal"
    ST = "st"
    STAR_ST = "star_st"
    DELISTING = "delisting"
    UNKNOWN = "unknown"


class CoreDiagnosticPool(StrEnum):
    BSE = "bse"
    NEW_STOCK = "new_stock"
    RISK_STATE = "risk_state"
    SUSPENDED = "suspended"
    COVERAGE = "coverage"


class CoreUniverseReason(StrEnum):
    NOT_POINT_IN_TIME_LISTED = "not_point_in_time_listed"
    OUTSIDE_U0_BOARD = "outside_u0_board"
    BSE_DIAGNOSTIC_ONLY = "bse_diagnostic_only"
    INSUFFICIENT_SEASONING = "insufficient_seasoning"
    ST_OR_STAR_ST = "st_or_star_st"
    DELISTING = "delisting"
    RISK_STATUS_UNKNOWN = "risk_status_unknown"
    SUSPENDED = "suspended"
    INSUFFICIENT_LIQUIDITY_HISTORY = "insufficient_liquidity_history"
    MEDIAN_AMOUNT_BELOW_FLOOR = "median_amount_below_floor"
    CRITICAL_PRICE_UNAVAILABLE = "critical_price_unavailable"


class FeatureAvailabilityState(StrEnum):
    VALUE = "value"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


class CoreInputLayer(StrEnum):
    COMPLETED_DAILY = "completed_daily"
    SEALED_INTRADAY_DIAGNOSTIC = "sealed_intraday_diagnostic"
    CURRENT_SESSION = "current_session"
    FORMING_MINUTE = "forming_minute"
    UNSEALED_TICK = "unsealed_tick"


class CoreUniverseSpec(ContractModel):
    universe_version: Literal["U0-v1"] = "U0-v1"
    allowed_boards: tuple[CoreBoard, ...] = (
        CoreBoard.SSE_MAIN,
        CoreBoard.SSE_STAR,
        CoreBoard.SZSE_MAIN,
        CoreBoard.SZSE_CHINEXT,
    )
    minimum_listed_common_sessions: Literal[252] = 252
    liquidity_window_common_sessions: Literal[20] = 20
    minimum_median_amount_cny: Literal[20_000_000] = 20_000_000


class CoreSecurityObservation(ContractModel):
    instrument_id: Identifier
    board: CoreBoard
    listed_on: date
    delisted_on: date | None = None
    available_at: AwareDatetime


class CoreRiskObservation(ContractModel):
    instrument_id: Identifier
    effective_on: date
    status: CoreRiskStatus
    suspended: bool
    available_at: AwareDatetime


class CoreDailyLiquidityObservation(ContractModel):
    instrument_id: Identifier
    trade_date: date
    amount_cny: int | None = Field(default=None, ge=0)
    has_legal_bar: bool
    available_at: AwareDatetime

    @model_validator(mode="after")
    def validate_amount(self) -> CoreDailyLiquidityObservation:
        if not self.has_legal_bar and self.amount_cny is not None:
            raise ValueError("illegal or missing bars cannot carry an amount")
        return self


class CoreUniverseDecision(ContractModel):
    instrument_id: Identifier
    decision_date: date
    input_cutoff: AwareDatetime
    universe_version: Literal["U0-v1"]
    research_member: bool
    new_risk_eligible: bool
    diagnostic_pool: tuple[CoreDiagnosticPool, ...]
    reason_codes: tuple[CoreUniverseReason, ...]
    listed_common_sessions: int = Field(ge=0)
    liquidity_observation_count: int = Field(ge=0, le=20)
    median_amount_20_cny: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_decision(self) -> CoreUniverseDecision:
        if self.new_risk_eligible and not self.research_member:
            raise ValueError("new-risk eligibility requires U0 research membership")
        if self.new_risk_eligible and (self.reason_codes or self.diagnostic_pool):
            raise ValueError("eligible decisions cannot carry exclusion diagnostics")
        return self


class CoreFeatureValue(ContractModel):
    feature_id: Identifier
    state: FeatureAvailabilityState
    value: float | None = None
    reason_code: Identifier | None = None

    @model_validator(mode="after")
    def validate_state_value(self) -> CoreFeatureValue:
        if self.state == FeatureAvailabilityState.VALUE and self.value is None:
            raise ValueError("value state requires a numeric value")
        if self.state != FeatureAvailabilityState.VALUE and self.value is not None:
            raise ValueError("missing and not-applicable states cannot be encoded as a number")
        if self.state != FeatureAvailabilityState.VALUE and self.reason_code is None:
            raise ValueError("non-value states require a stable reason code")
        return self


class CoreDataSemantics(ContractModel):
    version: Literal["core-data-semantics-v1"] = "core-data-semantics-v1"
    ohlc_source: Literal["continuous_research_price_index"] = (
        "continuous_research_price_index"
    )
    return_source: Literal["continuous_research_close"] = "continuous_research_close"
    vwap_source: Literal["raw_amount_div_raw_volume_scaled_to_research_index"] = (
        "raw_amount_div_raw_volume_scaled_to_research_index"
    )
    execution_source: Literal["point_in_time_raw_price_volume"] = (
        "point_in_time_raw_price_volume"
    )
    compatible_adjusted_price_use: Literal["audit_only"] = "audit_only"
    industry_taxonomy: Literal["SW2021-point-in-time-L1-L2-L3"] = (
        "SW2021-point-in-time-L1-L2-L3"
    )
    financial_date_only_rule: Literal["next_common_session_after_close"] = (
        "next_common_session_after_close"
    )
    feature_states: tuple[FeatureAvailabilityState, ...] = (
        FeatureAvailabilityState.VALUE,
        FeatureAvailabilityState.MISSING,
        FeatureAvailabilityState.NOT_APPLICABLE,
    )
    minimum_training_dates_coverage: float = Field(default=0.9, ge=0.0, le=1.0)
    minimum_cross_section_observed: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_coverage_gates(self) -> CoreDataSemantics:
        if (
            self.minimum_training_dates_coverage != 0.9
            or self.minimum_cross_section_observed != 0.8
        ):
            raise ValueError("core-data-semantics-v1 coverage gates are immutable")
        return self


class CoreDatasetSlice(ContractModel):
    dataset_name: Identifier
    dataset_version: Identifier
    schema_version: Version
    content_hash: ContentHash
    row_count: int = Field(ge=0)
    min_market_date: date
    max_market_date: date
    max_available_at: AwareDatetime
    input_layer: CoreInputLayer
    sealed: bool

    @model_validator(mode="after")
    def validate_range(self) -> CoreDatasetSlice:
        if self.min_market_date > self.max_market_date:
            raise ValueError("dataset date range is reversed")
        if self.input_layer == CoreInputLayer.SEALED_INTRADAY_DIAGNOSTIC and not self.sealed:
            raise ValueError("intraday diagnostics must be sealed")
        return self


class CoreInputSnapshot(ContractModel):
    core_input_snapshot_id: Identifier
    content_hash: ContentHash
    data_snapshot: DataSnapshot
    decision_date: date
    cutoff_at: AwareDatetime
    common_calendar_id: Identifier
    common_calendar_hash: ContentHash
    data_semantics_version: Literal["core-data-semantics-v1"]
    universe_version: Literal["U0-v1"]
    universe_content_hash: ContentHash
    datasets: tuple[CoreDatasetSlice, ...] = Field(min_length=1)


class CoreFeaturePackageSpec(ContractModel):
    package_id: Identifier
    canonical_dimension: int = Field(gt=0)
    authoritative_source: Identifier
    data_semantics_version: Literal["core-data-semantics-v1"]
    universe_version: Literal["U0-v1"]


__all__ = [
    "CoreBoard",
    "CoreDailyLiquidityObservation",
    "CoreDataSemantics",
    "CoreDatasetSlice",
    "CoreDiagnosticPool",
    "CoreFeaturePackageSpec",
    "CoreFeatureValue",
    "CoreInputLayer",
    "CoreInputSnapshot",
    "CoreRiskObservation",
    "CoreRiskStatus",
    "CoreSecurityObservation",
    "CoreUniverseDecision",
    "CoreUniverseReason",
    "CoreUniverseSpec",
    "FeatureAvailabilityState",
]
