"""Auditable adjacent-day percentile-turnover evidence."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from enum import StrEnum
from itertools import pairwise
from statistics import median
from typing import NamedTuple

from pydantic import Field, model_validator

from astramind_mini.contracts.base import ContractModel, Identifier

from ..feature_processing import CoreProcessedFeatureEnvelope
from .observations import observed_feature_map
from .statistics import average_ranks


class CoreTurnoverReason(StrEnum):
    AVAILABLE = "available"
    PREVIOUS_CROSS_SECTION_INSUFFICIENT = "previous_cross_section_insufficient"
    CURRENT_CROSS_SECTION_INSUFFICIENT = "current_cross_section_insufficient"
    COMMON_INSTRUMENTS_INSUFFICIENT = "common_instruments_insufficient"


class CoreTurnoverTransitionEvidence(ContractModel):
    previous_date: date
    current_date: date
    previous_n_day: int = Field(ge=0)
    current_n_day: int = Field(ge=0)
    n_common: int = Field(ge=0)
    turnover_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    valid: bool
    reason_code: CoreTurnoverReason

    @model_validator(mode="after")
    def validate_semantics(self) -> CoreTurnoverTransitionEvidence:
        if self.previous_date >= self.current_date:
            raise ValueError("turnover transition dates must be ascending")
        if self.n_common > min(self.previous_n_day, self.current_n_day):
            raise ValueError("turnover common count exceeds a daily cross-section")
        expected_valid = self.previous_n_day >= 2 and self.current_n_day >= 2 and self.n_common >= 5
        if self.valid != expected_valid or (self.turnover_ratio is not None) != expected_valid:
            raise ValueError("turnover validity or ratio is inconsistent")
        expected_reason = _turnover_reason(
            self.previous_n_day,
            self.current_n_day,
            self.n_common,
        )
        if self.reason_code != expected_reason:
            raise ValueError("turnover transition reason is inconsistent")
        return self


class _DailyTurnoverState(NamedTuple):
    decision_date: date
    observed_instruments: frozenset[str]
    percentiles: dict[str, float]


def feature_turnover(
    envelopes: Sequence[CoreProcessedFeatureEnvelope],
    *,
    feature_id: Identifier,
    minimum_common: int = 5,
    minimum_transitions: int = 60,
) -> tuple[float | None, int, tuple[CoreTurnoverTransitionEvidence, ...]]:
    """Return aggregate turnover plus every valid and invalid adjacent-day transition."""
    if minimum_common != 5 or minimum_transitions != 60:
        raise ValueError("core-feature-selection-v1 turnover constants are immutable")
    daily = tuple(
        _daily_state(envelope, feature_id)
        for envelope in sorted(envelopes, key=lambda item: item.decision_date)
    )
    evidence = tuple(_transition(previous, current) for previous, current in pairwise(daily))
    valid_ratios = tuple(
        float(item.turnover_ratio) for item in evidence if item.turnover_ratio is not None
    )
    aggregate = float(median(valid_ratios)) if len(valid_ratios) >= minimum_transitions else None
    return aggregate, len(valid_ratios), evidence


def _daily_percentiles(values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(values)
    if len(ordered) < 2:
        return {}
    ranks = average_ranks(tuple(values[item] for item in ordered))
    return {
        instrument: (rank - 1.0) / (len(ordered) - 1)
        for instrument, rank in zip(ordered, ranks, strict=True)
    }


def _daily_state(
    envelope: CoreProcessedFeatureEnvelope,
    feature_id: str,
) -> _DailyTurnoverState:
    values = observed_feature_map(envelope, feature_id)
    return _DailyTurnoverState(
        decision_date=envelope.decision_date,
        observed_instruments=frozenset(values),
        percentiles=_daily_percentiles(values),
    )


def _transition(
    previous: _DailyTurnoverState,
    current: _DailyTurnoverState,
) -> CoreTurnoverTransitionEvidence:
    previous_n_day = len(previous.observed_instruments)
    current_n_day = len(current.observed_instruments)
    common = tuple(sorted(previous.observed_instruments & current.observed_instruments))
    reason = _turnover_reason(previous_n_day, current_n_day, len(common))
    ratio = (
        sum(abs(current.percentiles[item] - previous.percentiles[item]) for item in common)
        / len(common)
        if reason == CoreTurnoverReason.AVAILABLE
        else None
    )
    return CoreTurnoverTransitionEvidence(
        previous_date=previous.decision_date,
        current_date=current.decision_date,
        previous_n_day=previous_n_day,
        current_n_day=current_n_day,
        n_common=len(common),
        turnover_ratio=ratio,
        valid=reason == CoreTurnoverReason.AVAILABLE,
        reason_code=reason,
    )


def _turnover_reason(
    previous_n_day: int,
    current_n_day: int,
    n_common: int,
) -> CoreTurnoverReason:
    if previous_n_day < 2:
        return CoreTurnoverReason.PREVIOUS_CROSS_SECTION_INSUFFICIENT
    if current_n_day < 2:
        return CoreTurnoverReason.CURRENT_CROSS_SECTION_INSUFFICIENT
    if n_common < 5:
        return CoreTurnoverReason.COMMON_INSTRUMENTS_INSUFFICIENT
    return CoreTurnoverReason.AVAILABLE


__all__ = [
    "CoreTurnoverReason",
    "CoreTurnoverTransitionEvidence",
    "feature_turnover",
]
