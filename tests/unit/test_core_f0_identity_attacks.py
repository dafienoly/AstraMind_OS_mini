from dataclasses import replace
from datetime import date

import pytest

from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITIONS,
    F0_FINANCIAL_COMPUTATION_SEMANTICS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
    F0_MARKET_OPERATOR_SEMANTICS,
    F0StatementKind,
    evaluate_astramind_f0,
    full_definition_manifest_hash,
    validate_f0_definition_manifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from tests.unit.test_core_f0_unit import (
    HASH,
    INSTRUMENTS,
    _bundle,
    _core_input,
    _row,
)


def test_current_u0_hash_and_all_daily_u0_identities_fail_closed() -> None:
    bundle = _bundle()
    wrong_core_input = _core_input(bundle.common_sessions, HASH)
    with pytest.raises(ValueError, match="current U0 content hash"):
        evaluate_astramind_f0(
            bundle.model_copy(update={"core_input": wrong_core_input})
        )

    current = next(
        item
        for item in bundle.universe_decisions
        if item.decision_date == bundle.core_input.decision_date
    )
    historical = next(
        item
        for item in bundle.universe_decisions
        if item.decision_date == bundle.common_sessions[0]
    )
    attacks = (
        current,
        current.model_copy(update={"research_member": not current.research_member}),
        historical,
        historical.model_copy(update={"research_member": not historical.research_member}),
    )
    for attack in attacks:
        with pytest.raises(ValueError, match="U0 decisions must be unique"):
            evaluate_astramind_f0(
                bundle.model_copy(
                    update={"universe_decisions": (*bundle.universe_decisions, attack)}
                )
            )


def test_flow_and_average_stock_periods_must_match_for_all_three_ratios() -> None:
    bundle = _bundle()
    shifted = tuple(
        fact.model_copy(
            update={
                "report_period": date(fact.report_period.year, 6, 30),
                "revision_id": f"q2-{fact.revision_id}",
            }
        )
        if fact.statement_kind == F0StatementKind.INSTANT
        else fact
        for fact in bundle.financial_facts
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": shifted})
    )

    assert _row(envelope, INSTRUMENTS[0], "BP").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )
    assert _row(envelope, INSTRUMENTS[0], "DEBT_TO_ASSETS").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )
    for feature in ("ROE_TTM", "ROA_TTM", "ACCRUALS_TO_ASSETS_TTM"):
        row = _row(envelope, INSTRUMENTS[0], feature)
        assert row.availability_state == FeatureAvailabilityState.MISSING
        assert row.missing_reason_code == "f0_financial_period_incomparable"


def test_financial_stable_identity_conflicts_fail_and_exact_duplicates_dedupe() -> None:
    bundle = _bundle()
    target = bundle.financial_facts[0]
    remaining = tuple(item for item in bundle.financial_facts if item is not target)
    conflict = target.model_copy(update={"value": target.value + 999.0})
    for pair in ((target, conflict), (conflict, target)):
        with pytest.raises(ValueError, match="conflicting financial facts"):
            evaluate_astramind_f0(
                bundle.model_copy(update={"financial_facts": (*remaining, *pair)})
            )

    baseline = evaluate_astramind_f0(bundle)
    duplicate_forward = evaluate_astramind_f0(
        bundle.model_copy(
            update={"financial_facts": (*bundle.financial_facts, target)}
        )
    )
    duplicate_reversed = evaluate_astramind_f0(
        bundle.model_copy(
            update={"financial_facts": (target, *reversed(bundle.financial_facts))}
        )
    )
    assert duplicate_forward.feature_snapshot.content_hash == (
        baseline.feature_snapshot.content_hash
    )
    assert duplicate_reversed.feature_snapshot.content_hash == (
        baseline.feature_snapshot.content_hash
    )


def test_market_operator_threshold_drift_changes_and_invalidates_manifest() -> None:
    assert F0_MARKET_OPERATOR_SEMANTICS.residual_minimum_observations == 15
    assert F0_MARKET_OPERATOR_SEMANTICS.residual_required_design_rank == 3
    assert F0_MARKET_OPERATOR_SEMANTICS.industry_relative_momentum_window == (60, 5)
    assert F0_MARKET_OPERATOR_SEMANTICS.liquidity_window_sessions == 20
    assert F0_MARKET_OPERATOR_SEMANTICS.amihud_scale == 1e8

    tampered = replace(
        F0_MARKET_OPERATOR_SEMANTICS,
        residual_minimum_observations=14,
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


def test_financial_operator_constants_are_part_of_the_manifest() -> None:
    assert F0_FINANCIAL_COMPUTATION_SEMANTICS.fiscal_year_end_month_day == (12, 31)
    assert F0_FINANCIAL_COMPUTATION_SEMANTICS.prior_year_offset == 1
    assert F0_FINANCIAL_COMPUTATION_SEMANTICS.average_stock_observations == 2
    assert F0_FINANCIAL_COMPUTATION_SEMANTICS.dividend_trailing_calendar_years == 1

    tampered = replace(
        F0_FINANCIAL_COMPUTATION_SEMANTICS,
        average_stock_observations=3,
    )
    assert full_definition_manifest_hash(
        F0_DEFINITIONS,
        financial_semantics=tampered,
    ) != F0_FULL_DEFINITION_MANIFEST_HASH
    with pytest.raises(ValueError, match="full definition manifest drifted"):
        validate_f0_definition_manifest(
            F0_DEFINITIONS,
            financial_semantics=tampered,
        )
