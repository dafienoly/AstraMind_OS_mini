from dataclasses import replace

import pytest

from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITIONS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
    F0_MARKET_OPERATOR_SEMANTICS,
    evaluate_astramind_f0,
    full_definition_manifest_hash,
    validate_f0_definition_manifest,
)
from astramind_mini.strategy_research.core.f0.market_reductions import (
    compound_returns,
)
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from tests.unit.test_core_f0_unit import INSTRUMENTS, _bundle, _row


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    (
        ("market_bar_selection", "tampered_bar_selection"),
        ("market_bar_equal_time_policy", "tampered_bar_tie_policy"),
        ("simple_return_operator", "tampered_return"),
        ("industry_relative_momentum_window", (59, 5)),
        ("industry_relative_return_observations", 54),
        ("window_endpoint_policy", "tampered_endpoints"),
        ("cross_section_reducer", "tampered_reducer"),
        ("cross_section_tie_policy", "tampered_ties"),
        ("cross_section_coverage_policy", "tampered_coverage"),
        ("missing_peer_bar_policy", "tampered_missing_peer"),
        ("industry_compounding_operator", "tampered_compounding"),
        ("ols_row_coverage_policy", "tampered_ols_coverage"),
        ("ols_solver", "tampered_solver"),
        ("ols_rcond", 1e-8),
        ("ols_design_columns", ("intercept", "tampered")),
        ("ols_rank_policy", "tampered_rank"),
        ("residual_required_design_rank", 2),
        ("ols_singular_policy", "tampered_singular"),
        ("ols_residual_reduction", "tampered_reduction"),
        ("residual_minimum_observations", 14),
    ),
)
def test_each_market_reduction_semantic_is_manifest_bound(
    field: str,
    tampered_value: object,
) -> None:
    tampered = replace(
        F0_MARKET_OPERATOR_SEMANTICS,
        **{field: tampered_value},
    )
    assert full_definition_manifest_hash(
        F0_DEFINITIONS,
        market_semantics=tampered,
    ) != F0_FULL_DEFINITION_MANIFEST_HASH
    with pytest.raises(ValueError, match="full definition manifest drifted"):
        validate_f0_definition_manifest(
            F0_DEFINITIONS,
            market_semantics=tampered,
        )


def test_industry_compounding_is_geometric_not_arithmetic() -> None:
    assert compound_returns((0.1, -0.1)) == pytest.approx(-0.01)


def test_missing_peer_bar_fails_industry_coverage_and_drops_ols_row() -> None:
    bundle = _bundle()
    target, peer = INSTRUMENTS[:2]
    missing_day = bundle.common_sessions[-10]
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == peer and bar.market_date == missing_day)
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"market_bars": bars})
    )
    relative = _row(envelope, target, "INDUSTRY_REL_MOM_60_5")
    assert relative.availability_state == FeatureAvailabilityState.MISSING
    assert relative.missing_reason_code == "f0_industry_return_unavailable"
    assert _row(envelope, target, "RESIDUAL_REV_20").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )


def test_missing_peer_rows_apply_the_frozen_ols_minimum() -> None:
    bundle = _bundle()
    target, peer = INSTRUMENTS[:2]
    missing_days = set(bundle.common_sessions[-8:])
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == peer and bar.market_date in missing_days)
    )
    residual = _row(
        evaluate_astramind_f0(bundle.model_copy(update={"market_bars": bars})),
        target,
        "RESIDUAL_REV_20",
    )
    assert residual.availability_state == FeatureAvailabilityState.MISSING
    assert residual.missing_reason_code == "f0_regression_observations_insufficient"


def test_rank_deficient_ols_is_explicitly_singular() -> None:
    bundle = _bundle()
    tail = set(bundle.common_sessions[-21:])
    constant_bars = tuple(
        bar.model_copy(
            update={
                "research_close": float(20 + INSTRUMENTS.index(bar.instrument_id))
            }
        )
        if bar.market_date in tail
        else bar
        for bar in bundle.market_bars
    )
    residual = _row(
        evaluate_astramind_f0(
            bundle.model_copy(update={"market_bars": constant_bars})
        ),
        INSTRUMENTS[0],
        "RESIDUAL_REV_20",
    )
    assert residual.availability_state == FeatureAvailabilityState.MISSING
    assert residual.missing_reason_code == "f0_regression_singular"


def test_equal_time_market_bar_ties_dedupe_or_fail_closed() -> None:
    bundle = _bundle()
    target = next(
        bar
        for bar in bundle.market_bars
        if bar.instrument_id == INSTRUMENTS[0]
        and bar.market_date == bundle.core_input.decision_date
    )
    baseline = evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    duplicate = bundle.model_copy(
        update={"market_bars": (*bundle.market_bars, target)}
    )
    assert evaluate_astramind_f0(duplicate).feature_snapshot.content_hash == baseline

    conflict = target.model_copy(
        update={"research_close": float(target.research_close) + 1.0}
    )
    for bars in (
        (*bundle.market_bars, conflict),
        (conflict, *reversed(bundle.market_bars)),
    ):
        with pytest.raises(ValueError, match="market bars conflict"):
            evaluate_astramind_f0(
                bundle.model_copy(update={"market_bars": bars})
            )
