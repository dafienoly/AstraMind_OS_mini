"""Immutable point-in-time forward-return label contracts."""

from __future__ import annotations

import math
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)

from ...application.identity import research_hash
from ..calendar import CoreCommonCalendar
from ..contracts import CoreUniverseDecision
from ..universe import core_universe_content_hash
from .ranking import average_rank_percentiles


class CoreLabelHorizon(StrEnum):
    D1 = "D1"
    D3 = "D3"
    D5 = "D5"
    H20 = "H20"
    H60 = "H60"

    @property
    def sessions(self) -> int:
        return int(self.value.removeprefix("D").removeprefix("H"))

    @property
    def selectable(self) -> bool:
        return self in {CoreLabelHorizon.H20, CoreLabelHorizon.H60}


class CoreLabelReason(StrEnum):
    NOT_MATURED = "not_matured"
    ENTRY_MISSING = "entry_missing"
    HORIZON_CLOSE_MISSING = "horizon_close_missing"
    NOT_RESEARCH_MEMBER = "not_research_member"
    CROSS_SECTION_INSUFFICIENT = "cross_section_insufficient"


class CoreForwardReturnLabelSpec(ContractModel):
    spec_version: Literal["core-forward-return-label-v1"] = "core-forward-return-label-v1"
    horizon: CoreLabelHorizon
    entry_offset_common_sessions: Literal[1] = 1
    entry_price: Literal["continuous_research_open"] = "continuous_research_open"
    terminal_price: Literal["continuous_research_close"] = "continuous_research_close"
    percentile_rule: Literal["average_rank_minus_1_over_n_minus_1"] = (
        "average_rank_minus_1_over_n_minus_1"
    )

    @model_validator(mode="after")
    def validate_fixed_v1(self) -> CoreForwardReturnLabelSpec:
        if (
            self.spec_version != "core-forward-return-label-v1"
            or self.horizon not in set(CoreLabelHorizon)
            or self.entry_offset_common_sessions != 1
            or self.entry_price != "continuous_research_open"
            or self.terminal_price != "continuous_research_close"
            or self.percentile_rule != "average_rank_minus_1_over_n_minus_1"
        ):
            raise ValueError("core-forward-return-label-v1 semantics are immutable")
        return self


class CoreForwardPriceObservation(ContractModel):
    instrument_id: Identifier
    trade_date: date
    research_open: float | None = None
    research_close: float | None = None
    available_at: AwareDatetime
    source_record_hash: ContentHash


class CoreForwardReturnLabelRow(ContractModel):
    instrument_id: Identifier
    research_member: bool
    absolute_return: float | None = None
    percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code: CoreLabelReason | None = None

    @model_validator(mode="after")
    def validate_state(self) -> CoreForwardReturnLabelRow:
        if self.absolute_return is not None and (
            not math.isfinite(self.absolute_return) or self.absolute_return <= -1.0
        ):
            raise ValueError("forward absolute return must be finite and greater than -1")
        if self.reason_code is None:
            if self.absolute_return is None or self.percentile is None:
                raise ValueError("valid label rows require return and percentile")
        elif self.percentile is not None:
            raise ValueError("invalid label rows cannot carry a percentile")
        if not self.research_member and self.reason_code != CoreLabelReason.NOT_RESEARCH_MEMBER:
            raise ValueError("non-members require not_research_member")
        if not self.research_member and self.absolute_return is not None:
            raise ValueError("non-members cannot carry a forward return")
        return self


class CoreForwardReturnLabelBatch(ContractModel):
    batch_id: Identifier
    content_hash: ContentHash
    spec: CoreForwardReturnLabelSpec
    decision_date: date
    common_calendar: CoreCommonCalendar
    entry_date: date | None
    horizon_close_date: date | None
    decision_universe_content_hash: ContentHash
    universe_rows: tuple[CoreUniverseDecision, ...] = Field(min_length=1)
    label_data_snapshot_id: Identifier
    label_data_snapshot_content_hash: ContentHash
    label_data_snapshot_as_of: AwareDatetime
    label_available_cutoff: AwareDatetime
    matured: bool
    n_universe_rows: int = Field(gt=0)
    n_research_members: int = Field(ge=0)
    n_valid_returns: int = Field(ge=0)
    label_coverage: float = Field(ge=0.0, le=1.0)
    rows: tuple[CoreForwardReturnLabelRow, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity_and_counts(self) -> CoreForwardReturnLabelBatch:
        CoreForwardReturnLabelSpec.model_validate(self.spec.model_dump())
        CoreCommonCalendar.model_validate(self.common_calendar.model_dump())
        _validate_label_calendar_and_maturity(self)
        ordered_universe = tuple(sorted(self.universe_rows, key=lambda item: item.instrument_id))
        ordered_rows = tuple(sorted(self.rows, key=lambda item: item.instrument_id))
        if self.universe_rows != ordered_universe or self.rows != ordered_rows:
            raise ValueError("label universe and rows must be canonical")
        if len({item.instrument_id for item in self.universe_rows}) != len(self.universe_rows):
            raise ValueError("label universe cannot contain duplicates")
        if tuple(item.instrument_id for item in self.rows) != tuple(
            item.instrument_id for item in self.universe_rows
        ):
            raise ValueError("label rows must exactly cover audited universe rows")
        if any(item.decision_date != self.decision_date for item in self.universe_rows):
            raise ValueError("label universe decision date mismatch")
        if core_universe_content_hash(self.universe_rows) != (self.decision_universe_content_hash):
            raise ValueError("label universe hash mismatch")
        _validate_label_rows_and_counts(self)
        expected_hash = research_hash(_label_batch_payload(self))
        expected_id = f"core-label-batch:{expected_hash.removeprefix('sha256:')}"
        if self.content_hash != expected_hash or self.batch_id != expected_id:
            raise ValueError("label batch canonical identity mismatch")
        return self

    @property
    def research_member_ids(self) -> tuple[str, ...]:
        return tuple(item.instrument_id for item in self.universe_rows if item.research_member)


def _validate_label_calendar_and_maturity(batch: CoreForwardReturnLabelBatch) -> None:
    sessions = batch.common_calendar.sessions
    if batch.decision_date not in sessions:
        raise ValueError("label decision date is absent from the bound common calendar")
    decision_index = sessions.index(batch.decision_date)
    entry_index = decision_index + batch.spec.entry_offset_common_sessions
    terminal_index = decision_index + batch.spec.horizon.sessions
    has_dates = entry_index < len(sessions) and terminal_index < len(sessions)
    expected_entry = sessions[entry_index] if has_dates else None
    expected_terminal = sessions[terminal_index] if has_dates else None
    if batch.entry_date != expected_entry or batch.horizon_close_date != expected_terminal:
        raise ValueError("label entry or horizon endpoint differs from the bound calendar")
    expected_matured = bool(
        has_dates
        and expected_terminal is not None
        and batch.label_data_snapshot_as_of <= batch.label_available_cutoff
        and batch.label_data_snapshot_as_of.date() >= expected_terminal
    )
    if batch.matured != expected_matured:
        raise ValueError("label maturity does not match calendar and snapshot cutoff")


def _validate_label_rows_and_counts(batch: CoreForwardReturnLabelBatch) -> None:
    membership = {item.instrument_id: item.research_member for item in batch.universe_rows}
    if any(item.research_member != membership[item.instrument_id] for item in batch.rows):
        raise ValueError("label row membership differs from the audited universe")
    valid = tuple(
        (item.instrument_id, float(item.absolute_return))
        for item in batch.rows
        if item.research_member and item.absolute_return is not None
    )
    percentiles = average_rank_percentiles(valid)
    for item in batch.rows:
        _validate_label_row_semantics(item, batch.matured, percentiles)
    members = sum(membership.values())
    expected_coverage = len(valid) / members if members else 0.0
    if (
        batch.n_universe_rows != len(batch.universe_rows)
        or batch.n_research_members != members
        or batch.n_valid_returns != len(valid)
        or batch.label_coverage != expected_coverage
    ):
        raise ValueError("label counts or coverage mismatch")


def _validate_label_row_semantics(
    row: CoreForwardReturnLabelRow,
    matured: bool,
    percentiles: dict[str, float],
) -> None:
    if not row.research_member:
        return
    if not matured:
        if (
            row.absolute_return is not None
            or row.percentile is not None
            or row.reason_code != CoreLabelReason.NOT_MATURED
        ):
            raise ValueError("immature labels cannot carry returns or percentiles")
        return
    if row.absolute_return is None:
        if row.reason_code not in {
            CoreLabelReason.ENTRY_MISSING,
            CoreLabelReason.HORIZON_CLOSE_MISSING,
        }:
            raise ValueError("mature missing label has an invalid reason")
        return
    expected = percentiles.get(row.instrument_id)
    expected_reason = None if expected is not None else CoreLabelReason.CROSS_SECTION_INSUFFICIENT
    if row.percentile != expected or row.reason_code != expected_reason:
        raise ValueError("label percentile or reason differs from recomputed average rank")


def _label_batch_payload(batch: CoreForwardReturnLabelBatch) -> dict[str, object]:
    return {
        "schema": "core-forward-return-label-batch-v1",
        "spec": batch.spec,
        "decision_date": batch.decision_date,
        "common_calendar": batch.common_calendar,
        "entry_date": batch.entry_date,
        "horizon_close_date": batch.horizon_close_date,
        "decision_universe_content_hash": batch.decision_universe_content_hash,
        "universe_rows": batch.universe_rows,
        "label_data_snapshot_id": batch.label_data_snapshot_id,
        "label_data_snapshot_content_hash": batch.label_data_snapshot_content_hash,
        "label_data_snapshot_as_of": batch.label_data_snapshot_as_of,
        "label_available_cutoff": batch.label_available_cutoff,
        "matured": batch.matured,
        "n_universe_rows": batch.n_universe_rows,
        "n_research_members": batch.n_research_members,
        "n_valid_returns": batch.n_valid_returns,
        "label_coverage": batch.label_coverage,
        "rows": batch.rows,
    }


__all__ = [
    "CoreForwardPriceObservation",
    "CoreForwardReturnLabelBatch",
    "CoreForwardReturnLabelRow",
    "CoreForwardReturnLabelSpec",
    "CoreLabelHorizon",
    "CoreLabelReason",
]
