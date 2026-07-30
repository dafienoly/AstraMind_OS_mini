"""Immutable contracts for the weekly core-research input waist."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, model_validator

from astramind_mini.contracts import DataSnapshot
from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)

from .calendar import CoreCommonCalendar
from .feature_values import FeatureAvailabilityState


class _ValidatedCopyContract(ContractModel):
    """Keep fixed v1 contracts valid when callers derive a copy."""

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        if not update:
            return super().model_copy(deep=deep)
        payload = self.model_dump()
        payload.update(update)
        return type(self).model_validate(payload)


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


class CoreInputLayer(StrEnum):
    COMPLETED_DAILY = "completed_daily"
    SEALED_INTRADAY_DIAGNOSTIC = "sealed_intraday_diagnostic"
    CURRENT_SESSION = "current_session"
    FORMING_MINUTE = "forming_minute"
    UNSEALED_TICK = "unsealed_tick"


class CoreUniverseSpec(_ValidatedCopyContract):
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

    @model_validator(mode="after")
    def validate_u0_v1(self) -> CoreUniverseSpec:
        expected_boards = (
            CoreBoard.SSE_MAIN,
            CoreBoard.SSE_STAR,
            CoreBoard.SZSE_MAIN,
            CoreBoard.SZSE_CHINEXT,
        )
        if (
            self.allowed_boards != expected_boards
            or self.minimum_listed_common_sessions != 252
            or self.liquidity_window_common_sessions != 20
            or self.minimum_median_amount_cny != 20_000_000
        ):
            raise ValueError("U0-v1 parameters and board order are immutable")
        return self


class CoreSecurityObservation(_ValidatedCopyContract):
    instrument_id: Identifier
    security_type: Literal["stock"] = "stock"
    share_class: Literal["a_share"] = "a_share"
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


class CoreDataSemantics(_ValidatedCopyContract):
    version: Literal["core-data-semantics-v1"] = "core-data-semantics-v1"
    ohlc_source: Literal["continuous_research_price_index"] = "continuous_research_price_index"
    return_source: Literal["continuous_research_close"] = "continuous_research_close"
    vwap_source: Literal["raw_amount_div_raw_volume_scaled_to_research_index"] = (
        "raw_amount_div_raw_volume_scaled_to_research_index"
    )
    execution_source: Literal["point_in_time_raw_price_volume"] = "point_in_time_raw_price_volume"
    compatible_adjusted_price_use: Literal["audit_only"] = "audit_only"
    industry_taxonomy: Literal["SW2021-point-in-time-L1-L2-L3"] = "SW2021-point-in-time-L1-L2-L3"
    financial_date_only_rule: Literal["next_common_session_after_close"] = (
        "next_common_session_after_close"
    )
    feature_states: tuple[FeatureAvailabilityState, ...] = (
        FeatureAvailabilityState.OBSERVED,
        FeatureAvailabilityState.MISSING,
        FeatureAvailabilityState.NOT_APPLICABLE,
    )
    minimum_training_dates_coverage: float = Field(default=0.9, ge=0.0, le=1.0)
    minimum_cross_section_observed: float = Field(default=0.8, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_coverage_gates(self) -> CoreDataSemantics:
        if (
            self.feature_states
            != (
                FeatureAvailabilityState.OBSERVED,
                FeatureAvailabilityState.MISSING,
                FeatureAvailabilityState.NOT_APPLICABLE,
            )
            or self.minimum_training_dates_coverage != 0.9
            or self.minimum_cross_section_observed != 0.8
        ):
            raise ValueError("core-data-semantics-v1 states and coverage gates are immutable")
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
    common_calendar: CoreCommonCalendar
    data_semantics_version: Literal["core-data-semantics-v1"]
    universe_version: Literal["U0-v1"]
    universe_content_hash: ContentHash
    datasets: tuple[CoreDatasetSlice, ...] = Field(min_length=1)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        if not update:
            return super().model_copy(deep=deep)
        payload = self.model_dump()
        payload.update(update)
        return type(self).model_validate(payload)

    @model_validator(mode="after")
    def validate_canonical_identity(self) -> CoreInputSnapshot:
        from .identity import canonical_core_input_identity

        ordered, content_hash, snapshot_id = canonical_core_input_identity(
            data_snapshot=self.data_snapshot,
            decision_date=self.decision_date,
            cutoff_at=self.cutoff_at,
            common_calendar=self.common_calendar,
            universe_content_hash=self.universe_content_hash,
            datasets=self.datasets,
        )
        if (
            self.datasets != ordered
            or self.content_hash != content_hash
            or self.core_input_snapshot_id != snapshot_id
        ):
            raise ValueError("CoreInputSnapshot canonical content identity mismatch")
        return self

    @property
    def common_calendar_id(self) -> str:
        return self.common_calendar.calendar_id

    @property
    def common_calendar_hash(self) -> str:
        return self.common_calendar.content_hash

    @property
    def common_sessions(self) -> tuple[date, ...]:
        return self.common_calendar.sessions


class CoreFeaturePackageSpec(_ValidatedCopyContract):
    package_id: Identifier
    canonical_dimension: int = Field(gt=0)
    authoritative_source: Identifier
    data_semantics_version: Literal["core-data-semantics-v1"]
    universe_version: Literal["U0-v1"]
    required_definition_registry_hash: ContentHash

    @model_validator(mode="after")
    def validate_canonical_package(self) -> CoreFeaturePackageSpec:
        expected = {
            "astramind-f0-v1": (
                24,
                "REQ-2026-0007-v2.3.0-section-6",
                "core-data-semantics-v1",
                "U0-v1",
                "sha256:5fd8435ecfd1dee75ca078a6aed7cfd47a257efa427394766938ba1fa5598b9b",
            ),
            "qlib-alpha158-79633dd": (
                158,
                "qlib-79633dd9506ea689e5400dea0197717b5b3d74b7",
                "core-data-semantics-v1",
                "U0-v1",
                "sha256:002151c6f808dc503b292caa604435f634d69672193288535f3fec504dd61c04",
            ),
            "formulaic-alpha101-v3": (
                101,
                "arxiv-1601.00991v3",
                "core-data-semantics-v1",
                "U0-v1",
                "sha256:6895ebea945ed4c95e43d8fd7d19cd97a77fb3a32f7868133c320a5f9ebde1c5",
            ),
        }
        if expected.get(self.package_id) != (
            self.canonical_dimension,
            self.authoritative_source,
            self.data_semantics_version,
            self.universe_version,
            self.required_definition_registry_hash,
        ):
            raise ValueError("unknown or altered canonical core feature package")
        return self


__all__ = [
    "CoreBoard",
    "CoreDailyLiquidityObservation",
    "CoreDataSemantics",
    "CoreDatasetSlice",
    "CoreDiagnosticPool",
    "CoreFeaturePackageSpec",
    "CoreInputLayer",
    "CoreInputSnapshot",
    "CoreRiskObservation",
    "CoreRiskStatus",
    "CoreSecurityObservation",
    "CoreUniverseDecision",
    "CoreUniverseReason",
    "CoreUniverseSpec",
]
