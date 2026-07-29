"""Strict observations and gate results for ETF model evidence."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
    Version,
)
from astramind_mini.data.contracts.observations import ObservationSource


class EtfOfficialBenchmarkObservation(ObservationSource):
    instrument_id: Identifier
    benchmark_code: Identifier
    benchmark_name: str
    effective_from: date
    historical_availability_known: bool
    evidence_kind: Literal["provider_current_registry"]


class EtfNavObservation(ObservationSource):
    instrument_id: Identifier
    nav_date: date
    announced_on: date
    unit_nav: float = Field(gt=0)
    accumulated_nav: float | None = Field(default=None, gt=0)
    adjusted_nav: float | None = Field(default=None, gt=0)


class OfficialIndexDailyObservation(ObservationSource):
    index_code: Identifier
    trade_date: date
    open: float | None = Field(default=None, gt=0)
    high: float | None = Field(default=None, gt=0)
    low: float | None = Field(default=None, gt=0)
    close: float = Field(gt=0)
    previous_close: float | None = Field(default=None, gt=0)
    change: float | None = None
    percent_change: float | None = None
    volume: float | None = Field(default=None, ge=0)
    amount: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> OfficialIndexDailyObservation:
        observed = tuple(
            value for value in (self.open, self.high, self.low, self.close) if value is not None
        )
        if self.high is not None and self.high < max(observed):
            raise ValueError("official index high is below OHLC values")
        if self.low is not None and self.low > min(observed):
            raise ValueError("official index low is above OHLC values")
        return self


class EtfSpreadMinuteObservation(ContractModel):
    provider: Identifier
    feed_session_id: ContentHash
    instrument_id: Identifier
    market_date: date
    minute: AwareDatetime
    first_market_time: AwareDatetime
    last_market_time: AwareDatetime
    quote_count: int = Field(ge=1)
    valid_quote_count: int = Field(ge=0)
    quoted_spread_bps_median: float | None = Field(default=None, ge=0)
    quoted_spread_bps_p90: float | None = Field(default=None, ge=0)
    available_at: AwareDatetime
    source_content_hash: ContentHash
    schema_version: Version

    @model_validator(mode="after")
    def validate_spreads(self) -> EtfSpreadMinuteObservation:
        if self.valid_quote_count > self.quote_count:
            raise ValueError("valid quote count cannot exceed quote count")
        values = (self.quoted_spread_bps_median, self.quoted_spread_bps_p90)
        if self.valid_quote_count == 0 and any(value is not None for value in values):
            raise ValueError("invalid minute cannot expose spread values")
        if self.valid_quote_count > 0 and any(value is None for value in values):
            raise ValueError("valid minute requires both spread statistics")
        if (
            self.quoted_spread_bps_median is not None
            and self.quoted_spread_bps_p90 is not None
            and self.quoted_spread_bps_p90 < self.quoted_spread_bps_median
        ):
            raise ValueError("spread p90 cannot be below median")
        return self


GateStatus = Literal["pass", "fail", "pending"]


class EtfModelDataGate(ContractModel):
    instrument_id: Identifier
    evidence_cutoff: date
    window_start: date | None = None
    window_end: date | None = None
    mapping_status: GateStatus
    official_benchmark_status: GateStatus
    nav_tradability_status: GateStatus
    spread_status: GateStatus
    open_session_count: int = Field(ge=0)
    qualifying_spread_session_count: int = Field(ge=0)
    planned_minutes_per_session: int = Field(default=240, ge=1)
    spread_minute_coverage_ratio: float | None = Field(default=None, ge=0, le=1)
    spread_median_bps: float | None = Field(default=None, ge=0)
    spread_p90_bps: float | None = Field(default=None, ge=0)
    ready: bool
    reason_codes: tuple[Identifier, ...] = ()
    evaluated_at: AwareDatetime
    schema_version: Version
    broker_actions_allowed: Literal[False] = False

    @model_validator(mode="after")
    def validate_ready(self) -> EtfModelDataGate:
        statuses = (
            self.mapping_status,
            self.official_benchmark_status,
            self.nav_tradability_status,
            self.spread_status,
        )
        if self.ready != all(status == "pass" for status in statuses):
            raise ValueError("ETF gate readiness must match all component gates")
        if not self.ready and not self.reason_codes:
            raise ValueError("blocked ETF gate requires reason codes")
        return self


__all__ = [
    "EtfModelDataGate",
    "EtfNavObservation",
    "EtfOfficialBenchmarkObservation",
    "EtfSpreadMinuteObservation",
    "GateStatus",
    "OfficialIndexDailyObservation",
]
