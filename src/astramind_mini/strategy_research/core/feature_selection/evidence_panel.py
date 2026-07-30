"""One-pass observed-state indexes for fold selection evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from statistics import median

from ..feature_processing import (
    CoreCrossSectionEvidence,
    CoreProcessedFeatureEnvelope,
)
from ..feature_values import FeatureAvailabilityState
from ..labels import CoreForwardReturnLabelBatch
from .coverage import (
    CoreCoverageReason,
    CoreDailyCoverageEvidence,
    CoreFoldCoverageEvidence,
)
from .models import CoreDailyRankICEvidence
from .statistics import average_ranks, spearman_by_key
from .turnover import CoreTurnoverReason, CoreTurnoverTransitionEvidence


@dataclass(frozen=True)
class _IndexedDay:
    envelope: CoreProcessedFeatureEnvelope
    cross_sections: dict[str, CoreCrossSectionEvidence]
    observed: dict[str, dict[str, float]]
    labels: dict[str, float]


@dataclass(frozen=True)
class SelectionEvidencePanel:
    """Pre-index immutable rows once; all formulas still use raw observed states."""

    days: tuple[_IndexedDay, ...]

    @classmethod
    def freeze(
        cls,
        envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
        labels: tuple[CoreForwardReturnLabelBatch, ...],
    ) -> SelectionEvidencePanel:
        return cls(
            days=tuple(
                _index_day(envelope, label)
                for envelope, label in zip(envelopes, labels, strict=True)
            )
        )

    def coverage(
        self,
        *,
        feature_id: str,
        definition_version: str,
    ) -> CoreFoldCoverageEvidence:
        daily = tuple(_daily_coverage(day, feature_id) for day in self.days)
        qualifying = sum(item.applicable_count > 0 for item in daily)
        passing = sum(item.passes_date_threshold for item in daily)
        ratio = passing / qualifying if qualifying else None
        passed = ratio is not None and ratio >= 0.9
        return CoreFoldCoverageEvidence.model_construct(
            feature_id=feature_id,
            feature_definition_version=definition_version,
            daily=daily,
            qualifying_date_count=qualifying,
            passing_date_count=passing,
            passing_date_ratio=ratio,
            passed=passed,
            reason_code=(
                CoreCoverageReason.PASSED
                if passed
                else (
                    CoreCoverageReason.NO_APPLICABLE_MEMBERS
                    if not qualifying
                    else CoreCoverageReason.COVERAGE_GATE_FAILED
                )
            ),
        )

    def daily_rank_ic(
        self,
        *,
        feature_id: str,
        direction: int,
    ) -> tuple[CoreDailyRankICEvidence, ...]:
        return tuple(_daily_rank_ic(day, feature_id, direction) for day in self.days)

    def turnover(
        self,
        *,
        feature_id: str,
        minimum_common: int,
        minimum_transitions: int,
    ) -> tuple[
        float | None,
        int,
        tuple[CoreTurnoverTransitionEvidence, ...],
    ]:
        states = tuple(
            (
                day.envelope.decision_date,
                day.observed[feature_id],
                _percentiles(day.observed[feature_id]),
            )
            for day in self.days
        )
        transitions = tuple(
            _turnover_transition(previous, current, minimum_common)
            for previous, current in pairwise(states)
        )
        valid = tuple(
            float(item.turnover_ratio) for item in transitions if item.turnover_ratio is not None
        )
        return (
            float(median(valid)) if len(valid) >= minimum_transitions else None,
            len(valid),
            transitions,
        )


def _index_day(
    envelope: CoreProcessedFeatureEnvelope,
    label: CoreForwardReturnLabelBatch,
) -> _IndexedDay:
    observed: dict[str, dict[str, float]] = {
        feature_id: {} for feature_id in envelope.feature_order
    }
    for row in envelope.rows:
        if (
            row.availability_state == FeatureAvailabilityState.OBSERVED
            and row.value_standardized_observed is not None
        ):
            observed[row.feature_id][row.instrument_id] = float(row.value_standardized_observed)
    labels = {
        row.instrument_id: float(row.percentile)
        for row in label.rows
        if row.research_member and row.percentile is not None
    }
    return _IndexedDay(
        envelope=envelope,
        cross_sections={item.feature_id: item for item in envelope.cross_sections},
        observed=observed,
        labels=labels,
    )


def _daily_coverage(
    day: _IndexedDay,
    feature_id: str,
) -> CoreDailyCoverageEvidence:
    cross = day.cross_sections[feature_id]
    coverage = cross.coverage
    passed = coverage is not None and coverage >= 0.8
    return CoreDailyCoverageEvidence.model_construct(
        decision_date=day.envelope.decision_date,
        observed_count=cross.observed_count,
        applicable_count=cross.applicable_count,
        coverage=coverage,
        passes_date_threshold=passed,
        reason_code=(
            CoreCoverageReason.PASSED
            if passed
            else (
                CoreCoverageReason.NO_APPLICABLE_MEMBERS
                if coverage is None
                else CoreCoverageReason.COVERAGE_GATE_FAILED
            )
        ),
    )


def _daily_rank_ic(
    day: _IndexedDay,
    feature_id: str,
    direction: int,
) -> CoreDailyRankICEvidence:
    values = day.observed[feature_id]
    pair_count = len(set(values) & set(day.labels))
    rank_ic = spearman_by_key(values, day.labels, minimum_pairs=2)
    return CoreDailyRankICEvidence.model_construct(
        decision_date=day.envelope.decision_date,
        pair_count=pair_count,
        rank_ic=rank_ic,
        signed_rank_ic=rank_ic * direction if rank_ic is not None else None,
    )


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    ordered = tuple(sorted(values))
    if len(ordered) < 2:
        return {}
    ranks = average_ranks(tuple(values[item] for item in ordered))
    return {
        instrument: (rank - 1.0) / (len(ordered) - 1)
        for instrument, rank in zip(ordered, ranks, strict=True)
    }


def _turnover_transition(
    previous: tuple[date, dict[str, float], dict[str, float]],
    current: tuple[date, dict[str, float], dict[str, float]],
    minimum_common: int,
) -> CoreTurnoverTransitionEvidence:
    previous_date, previous_values, previous_percentiles = previous
    current_date, current_values, current_percentiles = current
    common = tuple(sorted(set(previous_values) & set(current_values)))
    reason = _turnover_reason(
        len(previous_values),
        len(current_values),
        len(common),
        minimum_common,
    )
    ratio = (
        sum(abs(current_percentiles[item] - previous_percentiles[item]) for item in common)
        / len(common)
        if reason == CoreTurnoverReason.AVAILABLE
        else None
    )
    return CoreTurnoverTransitionEvidence.model_construct(
        previous_date=previous_date,
        current_date=current_date,
        previous_n_day=len(previous_values),
        current_n_day=len(current_values),
        n_common=len(common),
        turnover_ratio=ratio,
        valid=ratio is not None,
        reason_code=reason,
    )


def _turnover_reason(
    previous: int,
    current: int,
    common: int,
    minimum_common: int,
) -> CoreTurnoverReason:
    if previous < 2:
        return CoreTurnoverReason.PREVIOUS_CROSS_SECTION_INSUFFICIENT
    if current < 2:
        return CoreTurnoverReason.CURRENT_CROSS_SECTION_INSUFFICIENT
    if common < minimum_common:
        return CoreTurnoverReason.COMMON_INSTRUMENTS_INSUFFICIENT
    return CoreTurnoverReason.AVAILABLE


__all__ = ["SelectionEvidencePanel"]
