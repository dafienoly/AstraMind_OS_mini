from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest

from astramind_mini.strategy_research.core.contracts import CoreUniverseDecision
from astramind_mini.strategy_research.core.feature_processing import (
    CoreCrossSectionEvidence,
    CoreCrossSectionStatus,
    CoreNeutralizationStatus,
    CoreProcessedFeatureEnvelope,
    CoreProcessingControlRow,
    CoreProcessingSpec,
    neutralization_residuals,
    robust_cross_section,
    state_aware_imputation_values,
)
from astramind_mini.strategy_research.core.feature_selection import (
    calculate_fold_coverage,
)
from astramind_mini.strategy_research.core.feature_values import (
    CoreFeatureValue,
    CoreImputationSource,
    FeatureAvailabilityState,
)

NOW = datetime(2025, 1, 1, 16, tzinfo=UTC)


def _decision(instrument: str) -> CoreUniverseDecision:
    return CoreUniverseDecision(
        instrument_id=instrument,
        decision_date=NOW.date(),
        input_cutoff=NOW,
        universe_version="U0-v1",
        research_member=True,
        new_risk_eligible=True,
        diagnostic_pool=(),
        reason_codes=(),
        listed_common_sessions=300,
        liquidity_observation_count=20,
        median_amount_20_cny=30_000_000,
    )


def _control(instrument: str, industry: str, size: float) -> CoreProcessingControlRow:
    return CoreProcessingControlRow(
        instrument_id=instrument,
        decision_date=NOW.date(),
        universe_decision=_decision(instrument),
        sw_l1=industry,
        sw_l1_available_at=NOW,
        float_market_cap=math.exp(size),
        float_market_cap_available_at=NOW,
    )


def _raw(instrument: str, state: FeatureAvailabilityState) -> CoreFeatureValue:
    observed = state == FeatureAvailabilityState.OBSERVED
    return CoreFeatureValue(
        feature_snapshot_id="raw",
        instrument_id=instrument,
        decision_time=NOW,
        feature_definition_id="F",
        feature_definition_version="1.0.0",
        value_raw=1.0 if observed else None,
        availability_state=state,
        missing_reason_code=None if observed else "fixture_state",
        value_winsorized=None,
        value_standardized=None,
        imputation_source=CoreImputationSource.NONE,
        missing_indicator=state == FeatureAvailabilityState.MISSING,
        not_applicable_indicator=state == FeatureAvailabilityState.NOT_APPLICABLE,
        data_semantics_version="core-data-semantics-v1",
    )


def _cross(
    day: date,
    observed: int,
    missing: int,
    not_applicable: int,
) -> CoreProcessedFeatureEnvelope:
    applicable = observed + missing
    evidence = CoreCrossSectionEvidence(
        feature_id="F",
        feature_definition_version="1.0.0",
        observed_count=observed,
        missing_count=missing,
        not_applicable_count=not_applicable,
        applicable_count=applicable,
        coverage=observed / applicable if applicable else None,
        median_raw=None if observed == 0 else 1.0,
        mad_scale=None if observed == 0 else 0.0,
        winsor_lower=None if observed == 0 else 1.0,
        winsor_upper=None if observed == 0 else 1.0,
        status=(
            CoreCrossSectionStatus.NO_OBSERVED
            if observed == 0
            else CoreCrossSectionStatus.ZERO_SCALE
        ),
        neutralization_status=CoreNeutralizationStatus.INSUFFICIENT_SAMPLE,
        neutralization_sample_count=observed,
        neutralization_parameter_count=2,
    )
    return CoreProcessedFeatureEnvelope.model_construct(
        decision_date=day,
        cross_sections=(evidence,),
    )


def test_zero_mad_keeps_observed_values_and_sets_all_z_to_zero() -> None:
    result = robust_cross_section((1.0, 1.0, 1.0, 100.0), spec=CoreProcessingSpec())
    status, _, scale, _, _, winsorized, standardized = result
    assert status == CoreCrossSectionStatus.ZERO_SCALE
    assert scale == 0.0
    assert winsorized == (1.0, 1.0, 1.0, 100.0)
    assert standardized == (0.0, 0.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="non-finite"):
        robust_cross_section((1.0, math.inf), spec=CoreProcessingSpec())
    with pytest.raises(ValueError, match="immutable"):
        CoreProcessingSpec(neutralization_controls=("intercept",))


def test_industry_threshold_is_exact_and_na_always_uses_u0() -> None:
    observed_a = tuple(f"A{index}" for index in range(10))
    identifiers = (*observed_a, "B0", "MA", "MB", "NA")
    controls = {
        instrument: _control(
            instrument,
            "A" if instrument != "B0" and instrument != "MB" else "B",
            float(index + 1),
        )
        for index, instrument in enumerate(identifiers)
    }
    states = tuple(_raw(item, FeatureAvailabilityState.OBSERVED) for item in observed_a)
    states += (_raw("B0", FeatureAvailabilityState.OBSERVED),)
    states += (
        _raw("MA", FeatureAvailabilityState.MISSING),
        _raw("MB", FeatureAvailabilityState.MISSING),
        _raw("NA", FeatureAvailabilityState.NOT_APPLICABLE),
    )
    observed = {item: float(index) for index, item in enumerate(observed_a)}
    observed["B0"] = 100.0
    filled = state_aware_imputation_values(
        states,
        standardized_by_instrument=observed,
        controls=controls,
        spec=CoreProcessingSpec(),
    )
    assert filled["MA"] == (4.5, CoreImputationSource.SW_L1_MEDIAN)
    assert filled["MB"] == (5.0, CoreImputationSource.U0_MEDIAN)
    assert filled["NA"] == (5.0, CoreImputationSource.U0_MEDIAN)

    only_nine = {key: value for key, value in observed.items() if key != "A9"}
    filled_nine = state_aware_imputation_values(
        states,
        standardized_by_instrument=only_nine,
        controls=controls,
        spec=CoreProcessingSpec(),
    )
    assert filled_nine["MA"][1] == CoreImputationSource.U0_MEDIAN


def test_neutralization_exact_n_gate_and_rank_deficiency() -> None:
    controls = {
        f"S{index:02d}": _control(
            f"S{index:02d}",
            "A" if index < 8 else "B",
            float(index + 1),
        )
        for index in range(15)
    }
    observed = tuple(
        (
            instrument,
            2.0 + 0.5 * float(index + 1) + (3.0 if controls[instrument].sw_l1 == "B" else 0.0),
        )
        for index, instrument in enumerate(controls)
    )
    status, n, p, residuals = neutralization_residuals(
        observed,
        controls,
        spec=CoreProcessingSpec(),
    )
    assert (status, n, p) == (CoreNeutralizationStatus.AVAILABLE, 15, 3)
    assert max(abs(value) for value in residuals.values()) < 1e-12
    assert (
        neutralization_residuals(
            observed[:14],
            controls,
            spec=CoreProcessingSpec(),
        )[0]
        == CoreNeutralizationStatus.INSUFFICIENT_SAMPLE
    )

    collinear = {
        instrument: _control(
            instrument,
            str(control.sw_l1),
            0.0 if control.sw_l1 == "A" else 1.0,
        )
        for instrument, control in controls.items()
    }
    assert (
        neutralization_residuals(
            observed,
            collinear,
            spec=CoreProcessingSpec(),
        )[0]
        == CoreNeutralizationStatus.RANK_DEFICIENT
    )


def test_coverage_excludes_all_na_dates_and_honors_exact_boundary() -> None:
    start = date(2025, 1, 1)
    passing = [_cross(start + timedelta(days=index), 8, 2, 0) for index in range(9)]
    passing += [_cross(start + timedelta(days=9), 7, 3, 0)]
    passing += [_cross(start + timedelta(days=10), 0, 0, 10)]
    evidence = calculate_fold_coverage(feature_id="F", envelopes=passing)
    assert (
        evidence.passing_date_count,
        evidence.qualifying_date_count,
        evidence.passing_date_ratio,
        evidence.passed,
    ) == (9, 10, 0.9, True)
    failing = [_cross(start, 7, 3, 0), *passing[1:]]
    evidence = calculate_fold_coverage(feature_id="F", envelopes=failing)
    assert (evidence.passing_date_count, evidence.passing_date_ratio, evidence.passed) == (
        8,
        0.8,
        False,
    )
