from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from astramind_mini.strategy_research.core import FeatureAvailabilityState
from astramind_mini.strategy_research.core.f0 import (
    F0DividendFact,
    F0FinancialMetric,
    F0StatementKind,
    evaluate_astramind_f0,
)
from tests.unit.test_core_f0_unit import HASH, INSTRUMENTS, _bundle, _row

EDGE = json.loads(Path("tests/fixtures/core/f0/golden_case.json").read_text(encoding="utf-8"))[
    "edge_case_expectations"
]


def test_each_flow_metric_uses_its_own_latest_visible_ttm_period() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    revenue = next(
        fact
        for fact in bundle.financial_facts
        if fact.metric == F0FinancialMetric.REVENUE and fact.report_period == date(2023, 12, 31)
    )
    newer_revenue = revenue.model_copy(
        update={
            "report_period": date(2024, 12, 31),
            "value": 1600.0,
            "revision_id": "revenue-2024-fy",
            "announced_at": bundle.core_input.cutoff_at - timedelta(days=2),
        }
    )

    envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": (*bundle.financial_facts, newer_revenue)})
    )

    assert _row(envelope, target, "SP_TTM").value_raw == pytest.approx(1600 / 1e10)
    assert _row(envelope, target, "EP_TTM").value_raw == pytest.approx(141 / 1e10)
    margin = _row(envelope, target, "OPERATING_MARGIN_TTM")
    assert margin.availability_state == FeatureAvailabilityState.MISSING
    assert margin.missing_reason_code == "f0_financial_period_incomparable"


def test_incomplete_new_period_only_blocks_that_metric() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    incomplete_revenue = tuple(
        fact
        for fact in bundle.financial_facts
        if not (
            fact.metric == F0FinancialMetric.REVENUE and fact.report_period == date(2023, 9, 30)
        )
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": incomplete_revenue})
    )

    sp = _row(envelope, target, "SP_TTM")
    assert sp.availability_state == FeatureAvailabilityState.MISSING
    assert sp.missing_reason_code == "f0_financial_period_missing"
    assert _row(envelope, target, "EP_TTM").value_raw == pytest.approx(141 / 1e10)
    assert _row(envelope, target, "OCF_TTM_YOY").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )


def test_cross_field_financial_scope_mismatch_fails_closed() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    changed = tuple(
        fact.model_copy(update={"comparable_scope": "scope-b"})
        if fact.metric
        in {
            F0FinancialMetric.REVENUE,
            F0FinancialMetric.TOTAL_ASSETS,
        }
        else fact
        for fact in bundle.financial_facts
    )
    envelope = evaluate_astramind_f0(bundle.model_copy(update={"financial_facts": changed}))

    assert _row(envelope, target, "SP_TTM").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )
    for feature in ("ROA_TTM", "OPERATING_MARGIN_TTM", "DEBT_TO_ASSETS"):
        row = _row(envelope, target, feature)
        assert row.availability_state == FeatureAvailabilityState.MISSING
        assert row.missing_reason_code == "f0_financial_scope_incomparable"


def test_latest_visible_financial_revision_wins_without_rewriting_future() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    original = next(
        fact
        for fact in bundle.financial_facts
        if fact.metric == F0FinancialMetric.PARENT_NET_PROFIT
        and fact.report_period == date(2024, 9, 30)
    )
    visible_revision = original.model_copy(
        update={
            "value": 110.0,
            "revision_id": "parent-profit-q3-r2",
            "announced_at": bundle.core_input.cutoff_at - timedelta(days=3),
        }
    )
    future_revision = original.model_copy(
        update={
            "value": 999.0,
            "revision_id": "parent-profit-q3-r3",
            "announced_at": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(
            update={
                "financial_facts": (
                    *bundle.financial_facts,
                    visible_revision,
                    future_revision,
                )
            }
        )
    )
    assert _row(envelope, target, "EP_TTM").value_raw == pytest.approx(
        EDGE["visible_financial_revision_ep"]
    )


def test_dividend_events_use_latest_visible_revision_once() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    original = bundle.dividend_facts[0]
    visible_revision = original.model_copy(
        update={
            "cash_dividend_per_share": 0.6,
            "revision_id": "dividend-2024-final-r2",
            "announced_at": bundle.core_input.cutoff_at - timedelta(days=20),
        }
    )
    future_revision = original.model_copy(
        update={
            "cash_dividend_per_share": 9.9,
            "revision_id": "dividend-2024-final-r3",
            "announced_at": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    date_only_revision = F0DividendFact(
        **(
            original.model_dump(exclude={"announced_at", "announcement_date"})
            | {
                "revision_id": "dividend-2024-final-r4-date-only",
                "cash_dividend_per_share": 8.8,
                "announcement_date": bundle.core_input.decision_date,
            }
        )
    )
    second_event = F0DividendFact(
        instrument_id=target,
        event_id="dividend-2024-interim",
        revision_id="dividend-2024-interim-r1",
        cash_dividend_per_share=0.2,
        implementation_basis_at=bundle.core_input.cutoff_at - timedelta(days=30),
        announced_at=bundle.core_input.cutoff_at - timedelta(days=40),
        source_record_hash=HASH,
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(
            update={
                "dividend_facts": (
                    original,
                    visible_revision,
                    future_revision,
                    date_only_revision,
                    second_event,
                )
            }
        )
    )
    close = next(
        bar.research_close
        for bar in bundle.market_bars
        if bar.instrument_id == target and bar.market_date == bundle.core_input.decision_date
    )
    assert close is not None
    assert _row(envelope, target, "DY_TTM").value_raw == pytest.approx(
        EDGE["visible_dividend_revisions_total_dps"] / close
    )
    duplicate = bundle.model_copy(update={"dividend_facts": (original, original)})
    assert evaluate_astramind_f0(duplicate).feature_snapshot.content_hash == (
        evaluate_astramind_f0(bundle).feature_snapshot.content_hash
    )


def test_industry_applicability_precedes_stock_window_failures() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    missing_day = bundle.common_sessions[-10]
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == target and bar.market_date == missing_day)
    )
    memberships = tuple(
        item for item in bundle.industry_memberships if item.instrument_id != target
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"market_bars": bars, "industry_memberships": memberships})
    )
    for feature in ("INDUSTRY_REL_MOM_60_5", "RESIDUAL_REV_20"):
        row = _row(envelope, target, feature)
        assert row.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
        assert row.missing_reason_code == "f0_industry_membership_unavailable"


def test_zero_variance_zero_denominator_and_non_finite_inputs_are_explicit() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    constant_bars = tuple(
        bar.model_copy(update={"research_close": 25.0})
        if bar.instrument_id == target and bar.market_date in set(bundle.common_sessions[-21:])
        else bar
        for bar in bundle.market_bars
    )
    zero_assets = tuple(
        fact.model_copy(update={"value": 0.0})
        if fact.metric == F0FinancialMetric.TOTAL_ASSETS
        and fact.statement_kind == F0StatementKind.INSTANT
        else fact
        for fact in bundle.financial_facts
    )
    finite_envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"market_bars": constant_bars, "financial_facts": zero_assets})
    )
    assert (
        _row(finite_envelope, target, "REALIZED_VOL_20").value_raw
        == (EDGE["zero_variance_realized_vol"])
    )
    debt = _row(finite_envelope, target, "DEBT_TO_ASSETS")
    assert [debt.availability_state.value, debt.missing_reason_code] == (
        EDGE["zero_denominator_debt_to_assets"]
    )

    non_finite_bars = tuple(
        bar.model_copy(update={"raw_total_market_cap_cny": math.inf})
        if bar.instrument_id == target and bar.market_date == bundle.core_input.decision_date
        else bar
        for bar in bundle.market_bars
    )
    non_finite = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": non_finite_bars}))
    ep = _row(non_finite, target, "EP_TTM")
    assert [ep.availability_state.value, ep.missing_reason_code] == (
        EDGE["non_finite_market_cap_ep"]
    )
