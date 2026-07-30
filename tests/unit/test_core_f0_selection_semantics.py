from dataclasses import replace
from datetime import timedelta
from itertools import permutations

import pytest

from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITIONS,
    F0_FINANCIAL_COMPUTATION_SEMANTICS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
    F0CompanyClassification,
    F0CompanyType,
    evaluate_astramind_f0,
    full_definition_manifest_hash,
    validate_f0_definition_manifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from tests.unit.test_core_f0_unit import INSTRUMENTS, _bundle, _row


def _without_decision_bar(bundle, instrument_id):
    return tuple(
        bar
        for bar in bundle.market_bars
        if not (
            bar.instrument_id == instrument_id
            and bar.market_date == bundle.core_input.decision_date
        )
    )


def _without_classification(bundle, instrument_id):
    return tuple(
        item
        for item in bundle.company_classifications
        if item.instrument_id != instrument_id
    )


def test_market_bar_latest_layer_is_permutation_invariant() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    authoritative = next(
        bar
        for bar in bundle.market_bars
        if bar.instrument_id == target
        and bar.market_date == bundle.core_input.decision_date
    )
    base_bars = _without_decision_bar(bundle, target)
    stale_at = authoritative.available_at - timedelta(hours=1)
    stale_a = authoritative.model_copy(
        update={"available_at": stale_at, "research_close": 101.0}
    )
    stale_b = authoritative.model_copy(
        update={"available_at": stale_at, "research_close": 202.0}
    )
    expected = evaluate_astramind_f0(bundle).feature_snapshot.content_hash

    for ordering in permutations((authoritative, stale_a, stale_b)):
        actual = evaluate_astramind_f0(
            bundle.model_copy(update={"market_bars": (*base_bars, *ordering)})
        )
        assert actual.feature_snapshot.content_hash == expected


def test_market_bar_latest_ties_dedupe_or_fail_for_every_order() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    authoritative = next(
        bar
        for bar in bundle.market_bars
        if bar.instrument_id == target
        and bar.market_date == bundle.core_input.decision_date
    )
    base_bars = _without_decision_bar(bundle, target)
    expected = evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    for ordering in permutations((authoritative, authoritative)):
        actual = evaluate_astramind_f0(
            bundle.model_copy(update={"market_bars": (*base_bars, *ordering)})
        )
        assert actual.feature_snapshot.content_hash == expected

    conflict = authoritative.model_copy(
        update={"research_close": float(authoritative.research_close) + 1.0}
    )
    for ordering in permutations((authoritative, conflict)):
        with pytest.raises(ValueError, match="market bars conflict"):
            evaluate_astramind_f0(
                bundle.model_copy(update={"market_bars": (*base_bars, *ordering)})
            )


def test_financial_market_values_reuse_canonical_bar_selector() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    original = next(
        bar
        for bar in bundle.market_bars
        if bar.instrument_id == target
        and bar.market_date == bundle.core_input.decision_date
    )
    base_bars = _without_decision_bar(bundle, target)
    authoritative = original.model_copy(
        update={
            "available_at": original.available_at + timedelta(minutes=30),
            "research_close": 50.0,
            "raw_total_market_cap_cny": 20_000_000_000.0,
        }
    )
    stale_at = original.available_at - timedelta(hours=1)
    stale_a = original.model_copy(
        update={
            "available_at": stale_at,
            "research_close": 101.0,
            "raw_total_market_cap_cny": 30_000_000_000.0,
        }
    )
    stale_b = stale_a.model_copy(
        update={
            "research_close": 202.0,
            "raw_total_market_cap_cny": 40_000_000_000.0,
        }
    )

    for ordering in permutations((authoritative, stale_a, stale_b)):
        envelope = evaluate_astramind_f0(
            bundle.model_copy(update={"market_bars": (*base_bars, *ordering)})
        )
        assert _row(envelope, target, "EP_TTM").value_raw == pytest.approx(
            141 / 20_000_000_000
        )
        assert _row(envelope, target, "DY_TTM").value_raw == pytest.approx(0.5 / 50)


def test_classification_selection_handles_overlap_future_and_permutations() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    base_classifications = _without_classification(bundle, target)
    older = F0CompanyClassification(
        instrument_id=target,
        company_type=F0CompanyType.BANK,
        effective_from=bundle.common_sessions[-40],
        effective_to=bundle.core_input.decision_date,
        available_at=bundle.core_input.cutoff_at - timedelta(days=30),
    )
    newer = F0CompanyClassification(
        instrument_id=target,
        company_type=F0CompanyType.CORPORATE,
        effective_from=bundle.common_sessions[-20],
        available_at=bundle.core_input.cutoff_at - timedelta(days=10),
    )
    future = F0CompanyClassification(
        instrument_id=target,
        company_type=F0CompanyType.BANK,
        effective_from=bundle.common_sessions[-10],
        available_at=bundle.core_input.cutoff_at + timedelta(days=1),
    )

    for ordering in permutations((older, newer, future)):
        envelope = evaluate_astramind_f0(
            bundle.model_copy(
                update={
                    "company_classifications": (
                        *base_classifications,
                        *ordering,
                    )
                }
            )
        )
        assert _row(envelope, target, "EP_TTM").availability_state == (
            FeatureAvailabilityState.OBSERVED
        )


def test_classification_equal_latest_key_dedupes_or_fails_for_every_order() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    base_classifications = _without_classification(bundle, target)
    authoritative = F0CompanyClassification(
        instrument_id=target,
        company_type=F0CompanyType.CORPORATE,
        effective_from=bundle.common_sessions[-20],
        available_at=bundle.core_input.cutoff_at - timedelta(days=10),
    )
    for ordering in permutations((authoritative, authoritative)):
        envelope = evaluate_astramind_f0(
            bundle.model_copy(
                update={
                    "company_classifications": (
                        *base_classifications,
                        *ordering,
                    )
                }
            )
        )
        assert _row(envelope, target, "EP_TTM").availability_state == (
            FeatureAvailabilityState.OBSERVED
        )

    conflict = authoritative.model_copy(
        update={"company_type": F0CompanyType.BANK}
    )
    for ordering in permutations((authoritative, conflict)):
        with pytest.raises(ValueError, match="company classifications conflict"):
            evaluate_astramind_f0(
                bundle.model_copy(
                    update={
                        "company_classifications": (
                            *base_classifications,
                            *ordering,
                        )
                    }
                )
            )


def test_classification_same_effective_date_uses_latest_visible_availability() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    base_classifications = _without_classification(bundle, target)
    effective_from = bundle.common_sessions[-20]
    older = F0CompanyClassification(
        instrument_id=target,
        company_type=F0CompanyType.BANK,
        effective_from=effective_from,
        available_at=bundle.core_input.cutoff_at - timedelta(days=20),
    )
    authoritative = older.model_copy(
        update={
            "company_type": F0CompanyType.CORPORATE,
            "available_at": bundle.core_input.cutoff_at - timedelta(days=10),
        }
    )
    for ordering in permutations((older, authoritative)):
        envelope = evaluate_astramind_f0(
            bundle.model_copy(
                update={
                    "company_classifications": (
                        *base_classifications,
                        *ordering,
                    )
                }
            )
        )
        assert _row(envelope, target, "EP_TTM").availability_state == (
            FeatureAvailabilityState.OBSERVED
        )


@pytest.mark.parametrize(
    ("field", "tampered_value"),
    (
        ("classification_identity", "tampered_identity"),
        ("classification_interval_policy", "tampered_interval"),
        ("classification_selection", "tampered_selection"),
        ("classification_equal_key_policy", "tampered_tie_policy"),
    ),
)
def test_each_classification_semantic_is_manifest_bound(
    field: str,
    tampered_value: object,
) -> None:
    tampered = replace(
        F0_FINANCIAL_COMPUTATION_SEMANTICS,
        **{field: tampered_value},
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
