"""Processed-row profiles used by real Stage S selection parent fixtures."""

from __future__ import annotations

from statistics import median

from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureRow,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreImputationSource,
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.labels import CoreLabelHorizon

INSTRUMENTS = ("A", "B", "C", "D", "E", "F")


def feature_rows(
    *,
    feature_id: str,
    version: str,
    direction: int,
    feature_index: int,
    day_index: int,
    profile: str,
    horizon: CoreLabelHorizon,
) -> tuple[CoreProcessedFeatureRow, ...]:
    ranks = profile_ranks(profile, feature_index, day_index, horizon)
    return tuple(
        _observed_row(instrument, feature_id, version, rank * direction)
        if rank is not None
        else _unobserved_row(
            instrument,
            feature_id,
            version,
            FeatureAvailabilityState.NOT_APPLICABLE
            if profile == "golden" and feature_index == 3 and instrument == "D"
            else FeatureAvailabilityState.MISSING,
            model_value=(
                -999.0
                if profile == "golden"
                and feature_index == 0
                and day_index == 30
                and instrument == "F"
                else 0.0
            ),
        )
        for instrument, rank in zip(INSTRUMENTS, ranks, strict=True)
    )


def profile_ranks(
    profile: str,
    feature_index: int,
    day_index: int,
    horizon: CoreLabelHorizon,
) -> tuple[float | None, ...]:
    ascending = (0.0, 1.0, 2.0, 3.0, 4.0, 5.0)
    if profile == "single":
        return ascending if feature_index == 0 else (None,) * 6
    if profile == "complete_link":
        profiles = (
            ascending,
            (0.0, 1.0, 2.0, 3.0, 5.0, 4.0),
            (0.0, 1.0, 2.0, 4.0, 5.0, 3.0),
        )
        return profiles[feature_index] if feature_index < len(profiles) else (None,) * 6
    if profile == "golden":
        return _golden_ranks(ascending, feature_index, day_index, horizon)
    return (None,) * 6


def _golden_ranks(
    ascending: tuple[float, ...],
    feature_index: int,
    day_index: int,
    horizon: CoreLabelHorizon,
) -> tuple[float | None, ...]:
    forward = ascending if horizon == CoreLabelHorizon.H20 else tuple(reversed(ascending))
    if feature_index == 0:
        return (*forward[:5], None) if day_index == 30 else forward
    if feature_index == 1:
        return tuple(reversed(forward))
    if feature_index == 2:
        if day_index == 30:
            return (*forward[:5], None)
        return (
            (0.0, 1.0, 2.0, 4.0, 3.0, 5.0)
            if day_index == 90
            else forward
        )
    if feature_index == 3:
        return (0.0, None, None, None, None, None) if day_index == 60 else forward
    return (None,) * 6


def _observed_row(
    instrument: str,
    feature_id: str,
    version: str,
    value: float,
) -> CoreProcessedFeatureRow:
    return CoreProcessedFeatureRow(
        instrument_id=instrument,
        feature_id=feature_id,
        feature_definition_version=version,
        availability_state=FeatureAvailabilityState.OBSERVED,
        value_raw=value,
        value_winsorized=value,
        value_standardized_observed=value,
        model_value=value,
        imputation_source=CoreImputationSource.NONE,
        is_missing=False,
        is_not_applicable=False,
    )


def _unobserved_row(
    instrument: str,
    feature_id: str,
    version: str,
    state: FeatureAvailabilityState,
    *,
    model_value: float,
) -> CoreProcessedFeatureRow:
    return CoreProcessedFeatureRow(
        instrument_id=instrument,
        feature_id=feature_id,
        feature_definition_version=version,
        availability_state=state,
        missing_reason_code="fixture_unobserved",
        model_value=model_value,
        imputation_source=CoreImputationSource.U0_MEDIAN,
        is_missing=state == FeatureAvailabilityState.MISSING,
        is_not_applicable=state == FeatureAvailabilityState.NOT_APPLICABLE,
    )


def cross_section(
    feature_id: str,
    version: str,
    rows: tuple[CoreProcessedFeatureRow, ...],
) -> CoreCrossSectionEvidence:
    values = tuple(float(item.value_raw) for item in rows if item.value_raw is not None)
    missing_count = sum(item.is_missing for item in rows)
    not_applicable_count = sum(item.is_not_applicable for item in rows)
    applicable = len(rows) - not_applicable_count
    return CoreCrossSectionEvidence(
        feature_id=feature_id,
        feature_definition_version=version,
        observed_count=len(values),
        missing_count=missing_count,
        not_applicable_count=not_applicable_count,
        applicable_count=applicable,
        coverage=len(values) / applicable if applicable else None,
        median_raw=float(median(values)) if values else None,
        mad_scale=1.0 if values else None,
        winsor_lower=min(values) if values else None,
        winsor_upper=max(values) if values else None,
        status=(
            CoreCrossSectionStatus.READY
            if values
            else CoreCrossSectionStatus.NO_OBSERVED
        ),
        neutralization_status=CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
        neutralization_sample_count=len(values),
        neutralization_parameter_count=2,
    )


__all__ = ["INSTRUMENTS", "cross_section", "feature_rows", "profile_ranks"]
