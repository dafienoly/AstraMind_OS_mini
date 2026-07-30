"""Point-in-time daily panel and approved A-share input mapping."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from math import isfinite

from pydantic import Field, model_validator

from astramind_mini.contracts.base import AwareDatetime, ContractModel, Identifier

from ..contracts import CoreInputSnapshot
from ..semantics import IndustryMembershipObservation, select_point_in_time_industry
from .capabilities import L3_CAPABILITY_STATUS
from .input_identity import (
    canonical_alpha101_bar_content_hash,
    canonical_alpha101_industries,
    canonical_alpha101_industry_content_hash,
)
from .reasons import Alpha101Failure, Alpha101Reason
from .scalar_operators import divide, finite
from .universe import Alpha101UniverseHistory
from .values import Alpha101Cell, Matrix, missing


class Alpha101DailyObservation(ContractModel):
    instrument_id: Identifier
    trade_date: date
    available_at: AwareDatetime
    has_legal_bar: bool
    research_open_index: float | None = Field(default=None, gt=0)
    research_high_index: float | None = Field(default=None, gt=0)
    research_low_index: float | None = Field(default=None, gt=0)
    research_close_index: float | None = Field(default=None, gt=0)
    raw_close_cny: float | None = Field(default=None, gt=0)
    raw_volume_shares: float | None = Field(default=None, ge=0)
    raw_amount_cny: float | None = Field(default=None, ge=0)
    total_market_cap_cny: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_bar(self) -> Alpha101DailyObservation:
        research_prices = (
            self.research_open_index,
            self.research_high_index,
            self.research_low_index,
            self.research_close_index,
        )
        if self.has_legal_bar and any(value is None for value in research_prices):
            raise ValueError("legal bars require complete continuous research OHLC")
        if not self.has_legal_bar and any(value is not None for value in research_prices):
            raise ValueError("illegal bars cannot carry continuous research OHLC")
        if self.has_legal_bar:
            open_value, high, low, close = research_prices
            assert open_value is not None and high is not None
            assert low is not None and close is not None
            if high < max(open_value, close) or low > min(open_value, close):
                raise ValueError("continuous research OHLC is internally inconsistent")
        numeric = (
            *research_prices,
            self.raw_close_cny,
            self.raw_volume_shares,
            self.raw_amount_cny,
            self.total_market_cap_cny,
        )
        if any(value is not None and not isfinite(value) for value in numeric):
            raise ValueError("Alpha101 inputs must be finite")
        return self


class Alpha101Panel:
    def __init__(
        self,
        *,
        common_sessions: Sequence[date],
        universe_history: Alpha101UniverseHistory,
        bar_dataset_name: str,
        industry_dataset_name: str,
        instruments: Sequence[str],
        observations: Sequence[Alpha101DailyObservation],
        industries: Sequence[IndustryMembershipObservation],
    ) -> None:
        self.sessions = tuple(common_sessions)
        validated_universe = Alpha101UniverseHistory.model_validate(universe_history.model_dump())
        self.instruments = tuple(instruments)
        self.universe_history = validated_universe
        self.bar_dataset_name = bar_dataset_name
        self.industry_dataset_name = industry_dataset_name
        if not self.sessions or not self.instruments:
            raise ValueError("Alpha101 panel axes cannot be empty")
        dataset_names = {
            bar_dataset_name,
            industry_dataset_name,
            validated_universe.manifest.dataset_name,
        }
        if len(dataset_names) != 3:
            raise ValueError("Alpha101 bar, industry and U0 history slices must be distinct")
        if (
            len(set(self.sessions)) != len(self.sessions)
            or tuple(sorted(self.sessions)) != self.sessions
        ):
            raise ValueError("common sessions must be unique and ordered")
        if len(set(self.instruments)) != len(self.instruments):
            raise ValueError("instruments must be unique")
        if (
            validated_universe.common_sessions != self.sessions
            or validated_universe.instruments != self.instruments
        ):
            raise ValueError("U0 history must exactly match panel sessions and instruments")
        keyed = {(item.trade_date, item.instrument_id): item for item in observations}
        if len(keyed) != len(observations):
            raise ValueError("daily Alpha101 observations cannot be duplicated")
        expected = {(day, instrument) for day in self.sessions for instrument in self.instruments}
        if set(keyed) != expected:
            raise ValueError("Alpha101 panel must cover every session-instrument position")
        industry_rows = canonical_alpha101_industries(industries, self.instruments)
        self._members = tuple(
            validated_universe.members(index) for index in range(len(self.sessions))
        )
        self._daily_cutoffs = tuple(
            validated_universe.cutoff(index) for index in range(len(self.sessions))
        )
        self._validate_industry_ties(industry_rows)
        self._observations = keyed
        self._industries = industry_rows
        self._session_positions = {day: index for index, day in enumerate(self.sessions)}

    def members(self, session_index: int) -> tuple[bool, ...]:
        return self._members[session_index]

    @property
    def observations(self) -> tuple[Alpha101DailyObservation, ...]:
        return tuple(
            self._observations[(day, instrument)]
            for day in self.sessions
            for instrument in self.instruments
        )

    @property
    def industries(self) -> tuple[IndustryMembershipObservation, ...]:
        return self._industries

    @property
    def daily_cutoffs(self) -> tuple[datetime, ...]:
        return self._daily_cutoffs

    @property
    def bar_content_hash(self) -> str:
        return canonical_alpha101_bar_content_hash(
            sessions=self.sessions,
            instruments=self.instruments,
            observations=self.observations,
        )

    @property
    def industry_content_hash(self) -> str:
        return canonical_alpha101_industry_content_hash(
            sessions=self.sessions,
            instruments=self.instruments,
            industries=self.industries,
        )

    def validate_input_boundaries(self, core_input: CoreInputSnapshot) -> None:
        self._validate_internal_shape()
        datasets = {item.dataset_name: item for item in core_input.datasets}
        try:
            bar_dataset = datasets[self.bar_dataset_name]
            industry_dataset = datasets[self.industry_dataset_name]
            history_dataset = datasets[self.universe_history.manifest.dataset_name]
        except KeyError as error:
            raise ValueError("Alpha101 input dataset is absent from CoreInputSnapshot") from error
        if (
            bar_dataset.content_hash != self.bar_content_hash
            or bar_dataset.row_count != len(self._observations)
            or bar_dataset.min_market_date != self.sessions[0]
            or bar_dataset.max_market_date != self.sessions[-1]
        ):
            raise ValueError("Alpha101 bar rows do not match their frozen dataset slice")
        if (
            industry_dataset.content_hash != self.industry_content_hash
            or industry_dataset.row_count != len(self._industries)
        ):
            raise ValueError("Alpha101 industry rows do not match their frozen dataset slice")
        history = self.universe_history.manifest
        if (
            history_dataset.content_hash != history.history_content_hash
            or history_dataset.row_count != history.row_count
            or history_dataset.min_market_date != history.min_decision_date
            or history_dataset.max_market_date != history.max_decision_date
            or history_dataset.max_available_at != history.max_input_cutoff
            or not history_dataset.sealed
        ):
            raise ValueError("Alpha101 U0 history does not match its frozen dataset manifest")
        bar_dataset_cutoff = bar_dataset.max_available_at
        industry_dataset_cutoff = industry_dataset.max_available_at
        for item in self._observations.values():
            session_index = self._session_positions[item.trade_date]
            cutoff = min(
                self._daily_cutoffs[session_index],
                core_input.cutoff_at,
                bar_dataset_cutoff,
            )
            if item.available_at > cutoff:
                raise ValueError("Alpha101 bar crosses its point-in-time input cutoff")
        industry_cutoff = min(core_input.cutoff_at, industry_dataset_cutoff)
        if any(item.available_at > industry_cutoff for item in self._industries):
            raise ValueError("Alpha101 industry observation crosses the input cutoff")

    def _validate_internal_shape(self) -> None:
        expected = {(day, instrument) for day in self.sessions for instrument in self.instruments}
        if set(self._observations) != expected:
            raise ValueError("Alpha101 panel rows changed after construction")
        if (
            self.universe_history.common_sessions != self.sessions
            or self.universe_history.instruments != self.instruments
        ):
            raise ValueError("Alpha101 panel axes changed after construction")

    def _validate_industry_ties(
        self,
        industries: tuple[IndustryMembershipObservation, ...],
    ) -> None:
        for session_index, day in enumerate(self.sessions):
            cutoff = self._daily_cutoffs[session_index]
            for instrument in self.instruments:
                visible = [
                    item
                    for item in industries
                    if item.instrument_id == instrument
                    and item.valid_from <= day
                    and (item.valid_to is None or day < item.valid_to)
                    and item.available_at <= cutoff
                ]
                if not visible:
                    continue
                latest = max((item.valid_from, item.available_at) for item in visible)
                winners = [
                    item for item in visible if (item.valid_from, item.available_at) == latest
                ]
                if len(winners) > 1:
                    raise ValueError("ambiguous point-in-time Alpha101 industry membership")

    def input_matrix(self, name: str) -> Matrix:
        if name.startswith("adv"):
            return self._adv_matrix(int(name.removeprefix("adv")))
        rows = []
        for session_index, day in enumerate(self.sessions):
            rows.append(
                tuple(
                    self._input_cell(name, session_index, self._observations[(day, instrument)])
                    for instrument in self.instruments
                )
            )
        return tuple(rows)

    def industry_groups(self, session_index: int, level: str) -> tuple[str | None, ...]:
        if level == "subindustry":
            if L3_CAPABILITY_STATUS != "unavailable":
                raise ValueError("unknown Alpha101 L3 capability status")
            return tuple(None for _instrument in self.instruments)
        day = self.sessions[session_index]
        field = {"sector": "sw_l1", "industry": "sw_l2", "subindustry": "sw_l3"}[level]
        groups = []
        for instrument in self.instruments:
            selected = select_point_in_time_industry(
                self._industries,
                instrument_id=instrument,
                decision_date=day,
                cutoff_at=self._daily_cutoffs[session_index],
            )
            groups.append(getattr(selected, field) if selected is not None else None)
        return tuple(groups)

    def _input_cell(
        self,
        name: str,
        session_index: int,
        item: Alpha101DailyObservation,
    ) -> Alpha101Cell:
        if name in {"open", "high", "low", "close", "returns", "vwap"} and not item.has_legal_bar:
            return missing(Alpha101Reason.NO_LEGAL_BAR)
        if name == "returns":
            if session_index == 0:
                return missing(Alpha101Reason.WINDOW_INCOMPLETE)
            prior_day = self.sessions[session_index - 1]
            prior = self._observations[(prior_day, item.instrument_id)]
            if not prior.has_legal_bar:
                return missing(Alpha101Reason.NO_LEGAL_BAR)
            if prior.research_close_index is None or item.research_close_index is None:
                return missing(Alpha101Reason.INPUT_MISSING)
            return Alpha101Cell(divide(item.research_close_index, prior.research_close_index) - 1)
        if name == "vwap":
            values = (
                item.raw_amount_cny,
                item.raw_volume_shares,
                item.research_close_index,
                item.raw_close_cny,
            )
            if any(value is None for value in values):
                return missing(Alpha101Reason.INPUT_MISSING)
            try:
                raw_vwap = divide(item.raw_amount_cny or 0, item.raw_volume_shares or 0)
                return Alpha101Cell(
                    finite(
                        raw_vwap
                        * divide(
                            item.research_close_index or 0,
                            item.raw_close_cny or 0,
                        )
                    )
                )
            except Alpha101Failure as failure:
                return missing(failure.reason)
        attribute = {
            "open": "research_open_index",
            "high": "research_high_index",
            "low": "research_low_index",
            "close": "research_close_index",
            "volume": "raw_volume_shares",
            "cap": "total_market_cap_cny",
        }[name]
        value = getattr(item, attribute)
        return Alpha101Cell(value) if value is not None else missing(Alpha101Reason.INPUT_MISSING)

    def _adv_matrix(self, window: int) -> Matrix:
        result = []
        for session_index, _day in enumerate(self.sessions):
            row = []
            for instrument in self.instruments:
                if session_index + 1 < window:
                    row.append(missing(Alpha101Reason.WINDOW_INCOMPLETE))
                    continue
                days = self.sessions[session_index - window + 1 : session_index + 1]
                amounts = [self._observations[(item, instrument)].raw_amount_cny for item in days]
                if any(value is None for value in amounts):
                    row.append(missing(Alpha101Reason.INPUT_MISSING))
                else:
                    try:
                        average = finite(sum(value or 0 for value in amounts) / window)
                        row.append(Alpha101Cell(average))
                    except Alpha101Failure as failure:
                        row.append(missing(failure.reason))
            result.append(tuple(row))
        return tuple(result)


__all__ = [
    "Alpha101DailyObservation",
    "Alpha101Panel",
]
