from datetime import timedelta

import pytest

from astramind_mini.strategy_research.core.f0 import evaluate_astramind_f0
from tests.unit.test_core_f0_unit import _bundle


def test_same_stable_revision_rejects_any_financial_or_dividend_field_change() -> None:
    bundle = _bundle()
    financial = bundle.financial_facts[0]
    dividend = bundle.dividend_facts[0]
    attacks = (
        (
            "financial_facts",
            financial,
            financial.model_copy(
                update={"announced_at": financial.announced_at + timedelta(minutes=1)}
            ),
            "conflicting financial facts",
        ),
        (
            "financial_facts",
            financial,
            financial.model_copy(update={"value": financial.value + 1.0}),
            "conflicting financial facts",
        ),
        (
            "dividend_facts",
            dividend,
            dividend.model_copy(
                update={"announced_at": dividend.announced_at + timedelta(minutes=1)}
            ),
            "conflicting dividend facts",
        ),
        (
            "dividend_facts",
            dividend,
            dividend.model_copy(
                update={"cash_dividend_per_share": dividend.cash_dividend_per_share + 0.1}
            ),
            "conflicting dividend facts",
        ),
    )
    for field, original, changed, message in attacks:
        base = getattr(bundle, field)
        for pair in ((original, changed), (changed, original)):
            with pytest.raises(ValueError, match=message):
                evaluate_astramind_f0(
                    bundle.model_copy(update={field: (*base, *pair)})
                )


def test_identical_financial_and_dividend_duplicates_merge_in_both_orders() -> None:
    bundle = _bundle()
    financial = bundle.financial_facts[0]
    dividend = bundle.dividend_facts[0]
    baseline = evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    variants = (
        bundle.model_copy(
            update={
                "financial_facts": (*bundle.financial_facts, financial),
                "dividend_facts": (*bundle.dividend_facts, dividend),
            }
        ),
        bundle.model_copy(
            update={
                "financial_facts": tuple(
                    reversed((*bundle.financial_facts, financial))
                ),
                "dividend_facts": tuple(
                    reversed((*bundle.dividend_facts, dividend))
                ),
            }
        ),
    )
    assert {
        evaluate_astramind_f0(item).feature_snapshot.content_hash for item in variants
    } == {baseline}


def test_equal_time_financial_revisions_are_name_and_order_independent() -> None:
    bundle = _bundle()
    original = bundle.financial_facts[0]
    baseline = evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    for revision_id in ("aaa-renamed", "zzz-renamed"):
        same_payload = original.model_copy(update={"revision_id": revision_id})
        for facts in (
            (*bundle.financial_facts, same_payload),
            (same_payload, *reversed(bundle.financial_facts)),
        ):
            assert evaluate_astramind_f0(
                bundle.model_copy(update={"financial_facts": facts})
            ).feature_snapshot.content_hash == baseline

    conflict = original.model_copy(
        update={"revision_id": "conflict", "value": original.value + 1.0}
    )
    for facts in (
        (*bundle.financial_facts, conflict),
        (conflict, *reversed(bundle.financial_facts)),
    ):
        with pytest.raises(ValueError, match="latest availability"):
            evaluate_astramind_f0(
                bundle.model_copy(update={"financial_facts": facts})
            )


def test_equal_time_dividend_revisions_are_name_and_order_independent() -> None:
    bundle = _bundle()
    original = bundle.dividend_facts[0]
    baseline = evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    for revision_id in ("aaa-renamed", "zzz-renamed"):
        same_payload = original.model_copy(update={"revision_id": revision_id})
        for facts in (
            (*bundle.dividend_facts, same_payload),
            (same_payload, *reversed(bundle.dividend_facts)),
        ):
            assert evaluate_astramind_f0(
                bundle.model_copy(update={"dividend_facts": facts})
            ).feature_snapshot.content_hash == baseline

    conflict = original.model_copy(
        update={
            "revision_id": "conflict",
            "cash_dividend_per_share": original.cash_dividend_per_share + 0.1,
        }
    )
    for facts in (
        (*bundle.dividend_facts, conflict),
        (conflict, *reversed(bundle.dividend_facts)),
    ):
        with pytest.raises(ValueError, match="latest availability"):
            evaluate_astramind_f0(
                bundle.model_copy(update={"dividend_facts": facts})
            )
