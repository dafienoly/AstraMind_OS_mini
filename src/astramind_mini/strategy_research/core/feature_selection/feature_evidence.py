"""Single-feature fold evidence: coverage, RankIC, bootstrap and stability."""

from __future__ import annotations

import math
from collections.abc import Sequence

from ..feature_processing import CoreProcessedFeatureEnvelope
from ..labels import CoreForwardReturnLabelBatch, CoreLabelHorizon
from .bootstrap import centered_circular_block_bootstrap, selection_seed
from .coverage import calculate_fold_coverage
from .metrics import feature_turnover, observed_feature_map
from .models import (
    CoreDailyRankICEvidence,
    CoreFeatureSelectionEvidence,
    CoreSelectionReason,
    CoreSelectionSpec,
    CoreSubfoldRankICEvidence,
)
from .plan import CoreSelectionFold
from .priors import CoreSelectionPriorEntry
from .statistics import finite_mean, median_absolute_deviation, spearman_by_key


def build_initial_feature_evidence(
    *,
    prior: CoreSelectionPriorEntry,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    labels: tuple[CoreForwardReturnLabelBatch, ...],
    fold: CoreSelectionFold,
    horizon: CoreLabelHorizon,
    spec: CoreSelectionSpec,
) -> CoreFeatureSelectionEvidence:
    coverage = calculate_fold_coverage(feature_id=prior.feature_id, envelopes=envelopes)
    daily = tuple(
        _daily_rank_ic(
            envelope=envelope,
            label=label,
            feature_id=prior.feature_id,
            direction=prior.expected_direction,
        )
        for envelope, label in zip(envelopes, labels, strict=True)
    )
    by_date = {item.decision_date: item.signed_rank_ic for item in daily}
    subfolds = tuple(
        summarize_subfold_rankic(
            subfold.subfold_id,
            tuple(by_date[day] for day in subfold.decision_dates),
            spec.minimum_subfold_valid_rankic,
        )
        for subfold in fold.subfolds
    )
    sufficient = all(item.sample_sufficient for item in subfolds)
    signed_values = tuple(
        float(item.signed_rank_ic) for item in daily if item.signed_rank_ic is not None
    )
    eligible = coverage.passed and sufficient and bool(signed_values)
    seed: int | None = None
    p_value: float | None = None
    signed_mean = finite_mean(signed_values)
    if eligible:
        seed = selection_seed(
            prior.feature_id,
            prior.definition_version,
            horizon.value,
            fold.fold_id,
        )
        p_value = centered_circular_block_bootstrap(
            signed_values,
            seed=seed,
            block_length=spec.bootstrap_block_length,
            replicates=spec.bootstrap_replicates,
        ).p_value
        eligible = math.isfinite(p_value)
    turnover, transition_count, stability = _quality_metrics(
        prior.feature_id,
        envelopes,
        signed_values,
        spec,
    )
    reason = _eligibility_reason(coverage.passed, sufficient, eligible)
    return CoreFeatureSelectionEvidence(
        feature_key=prior.feature_key,
        feature_id=prior.feature_id,
        definition_version=prior.definition_version,
        canonical_order=prior.canonical_order,
        expected_direction=prior.expected_direction,
        complexity=prior.complexity,
        coverage=coverage,
        daily_rank_ic=daily,
        subfolds=subfolds,  # type: ignore[arg-type]
        direction_consistent=subfold_direction_consistent(subfolds),
        signed_mean_rank_ic=signed_mean,
        bootstrap_seed=seed,
        bootstrap_p_value=p_value,
        selection_eligible=eligible,
        bh_passed=False,
        coverage_mean=coverage.mean_qualifying_coverage,
        turnover=turnover,
        turnover_valid_transitions=transition_count,
        stability=stability,
        reason_code=reason,
    )


def _quality_metrics(
    feature_id: str,
    envelopes: tuple[CoreProcessedFeatureEnvelope, ...],
    signed_values: tuple[float, ...],
    spec: CoreSelectionSpec,
) -> tuple[float | None, int, float | None]:
    turnover, transition_count = feature_turnover(
        envelopes,
        feature_id=feature_id,
        minimum_common=spec.turnover_minimum_common_instruments,
        minimum_transitions=spec.turnover_minimum_valid_transitions,
    )
    mad = median_absolute_deviation(signed_values)
    return turnover, transition_count, 1.0 / (1.0 + mad) if mad is not None else None


def _daily_rank_ic(
    *,
    envelope: CoreProcessedFeatureEnvelope,
    label: CoreForwardReturnLabelBatch,
    feature_id: str,
    direction: int,
) -> CoreDailyRankICEvidence:
    feature_values = observed_feature_map(envelope, feature_id)
    label_values = {
        item.instrument_id: float(item.percentile)
        for item in label.rows
        if item.research_member and item.percentile is not None
    }
    pair_count = len(set(feature_values) & set(label_values))
    rank_ic = spearman_by_key(feature_values, label_values, minimum_pairs=2)
    return CoreDailyRankICEvidence(
        decision_date=envelope.decision_date,
        pair_count=pair_count,
        rank_ic=rank_ic,
        signed_rank_ic=(rank_ic * direction if rank_ic is not None else None),
    )


def summarize_subfold_rankic(
    subfold_id: str,
    values: Sequence[float | None],
    minimum_count: int,
) -> CoreSubfoldRankICEvidence:
    valid = tuple(float(item) for item in values if item is not None)
    return CoreSubfoldRankICEvidence(
        subfold_id=subfold_id,
        valid_count=len(valid),
        signed_mean_rank_ic=finite_mean(valid),
        sample_sufficient=len(valid) >= minimum_count,
    )


def subfold_direction_consistent(
    subfolds: Sequence[CoreSubfoldRankICEvidence],
) -> bool:
    return all(
        item.sample_sufficient
        and item.signed_mean_rank_ic is not None
        and item.signed_mean_rank_ic > 0.0
        for item in subfolds
    )


def _eligibility_reason(
    coverage_passed: bool,
    samples_sufficient: bool,
    eligible: bool,
) -> CoreSelectionReason:
    if not coverage_passed:
        return CoreSelectionReason.COVERAGE_GATE_FAILED
    if not samples_sufficient:
        return CoreSelectionReason.SUBFOLD_SAMPLE_INSUFFICIENT
    if not eligible:
        return CoreSelectionReason.P_VALUE_UNAVAILABLE
    return CoreSelectionReason.BH_REJECTED


__all__ = [
    "build_initial_feature_evidence",
    "subfold_direction_consistent",
    "summarize_subfold_rankic",
]
