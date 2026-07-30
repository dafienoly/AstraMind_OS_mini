"""Cohesive deterministic fixture builders and F0 boundary proofs share one module."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core import (
    CoreDatasetSlice,
    CoreInputLayer,
    CoreUniverseDecision,
    FeatureAvailabilityState,
    core_universe_content_hash,
    freeze_core_input_snapshot,
)
from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITION_REGISTRY_HASH,
    F0_DEFINITIONS,
    F0CompanyClassification,
    F0CompanyType,
    F0DividendFact,
    F0FinancialFact,
    F0FinancialMetric,
    F0InputBundle,
    F0MarketBar,
    F0StatementKind,
    evaluate_astramind_f0,
)
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    ASTRAMIND_F0_FEATURE_ORDER,
)
from astramind_mini.strategy_research.core.semantics import (
    IndustryMembershipObservation,
)

TZ = ZoneInfo("Asia/Shanghai")
HASH = "sha256:" + "a" * 64
INSTRUMENTS = tuple(f"60000{index}.SH" for index in range(6))
INDUSTRIES = ("sw-bank", "sw-tech", "sw-consumer")
GOLDEN_FIXTURE = Path("tests/fixtures/core/f0/golden_case.json")


def _sessions(count: int = 260) -> tuple[date, ...]:
    fixture = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))
    sessions = tuple(date.fromisoformat(value) for value in fixture["common_sessions"])
    if count != len(sessions):
        raise ValueError("F0 tests require the fixed 260-session SSE/SZSE calendar")
    return sessions


def _core_input(
    sessions: tuple[date, ...],
    universe_content_hash: str,
):
    cutoff = datetime.combine(sessions[-1], datetime.min.time(), TZ).replace(hour=18)
    snapshot = DataSnapshot(
        snapshot_id="snapshot:f0-test",
        as_of=cutoff - timedelta(minutes=30),
        datasets=(
            DatasetRef(
                dataset_name="f0_fixture",
                dataset_version="v1",
                schema_version="1.0.0",
                content_hash=HASH,
            ),
        ),
        known_gaps=(),
        created_at=cutoff - timedelta(minutes=15),
        code_identity="f0-test",
    )
    dataset = CoreDatasetSlice(
        dataset_name="f0_fixture",
        dataset_version="v1",
        schema_version="1.0.0",
        content_hash=HASH,
        row_count=1000,
        min_market_date=sessions[0],
        max_market_date=sessions[-1],
        max_available_at=cutoff - timedelta(hours=1),
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    return freeze_core_input_snapshot(
        data_snapshot=snapshot,
        decision_date=sessions[-1],
        cutoff_at=cutoff,
        common_calendar_id="fixture-calendar",
        common_sessions=sessions,
        universe_content_hash=universe_content_hash,
        datasets=(dataset,),
    )


def _decisions(sessions: tuple[date, ...]) -> tuple[CoreUniverseDecision, ...]:
    return tuple(
        CoreUniverseDecision(
            instrument_id=instrument,
            decision_date=day,
            input_cutoff=datetime.combine(day, datetime.min.time(), TZ).replace(hour=18),
            universe_version="U0-v1",
            research_member=(
                instrument != INSTRUMENTS[-1] or day >= sessions[min(60, len(sessions) - 1)]
            ),
            new_risk_eligible=(
                instrument != INSTRUMENTS[-1] or day >= sessions[min(60, len(sessions) - 1)]
            ),
            diagnostic_pool=(),
            reason_codes=(),
            listed_common_sessions=300,
            liquidity_observation_count=20,
            median_amount_20_cny=50_000_000,
        )
        for day in sessions
        for instrument in INSTRUMENTS
    )


def _bars(sessions: tuple[date, ...]) -> tuple[F0MarketBar, ...]:
    rows = []
    for ordinal, day in enumerate(sessions):
        for index, instrument in enumerate(INSTRUMENTS):
            daily = 0.0004 * (index + 1) + 0.002 * math.sin((ordinal + index) / 7)
            close = (20 + index) * math.exp(0.0007 * ordinal + daily)
            rows.append(
                F0MarketBar(
                    instrument_id=instrument,
                    market_date=day,
                    available_at=datetime.combine(day, datetime.min.time(), TZ).replace(hour=16),
                    research_close=close,
                    amount_cny=40_000_000 + index * 3_000_000 + ordinal * 10_000,
                    turnover_rate=0.01 + index * 0.001 + ordinal * 0.00001,
                    raw_total_market_cap_cny=(10 + index) * 1_000_000_000,
                    source_record_hash=HASH,
                )
            )
    return tuple(rows)


def _financial_facts(cutoff: datetime) -> tuple[F0FinancialFact, ...]:
    periods = (
        (date(2022, 9, 30), 70.0),
        (date(2022, 12, 31), 100.0),
        (date(2023, 9, 30), 84.0),
        (date(2023, 12, 31), 120.0),
        (date(2024, 9, 30), 105.0),
    )
    multipliers = {
        F0FinancialMetric.PARENT_NET_PROFIT: 1.0,
        F0FinancialMetric.NET_PROFIT: 1.1,
        F0FinancialMetric.REVENUE: 10.0,
        F0FinancialMetric.OPERATING_PROFIT: 1.5,
        F0FinancialMetric.OPERATING_CASH_FLOW: 1.2,
    }
    rows = [
        F0FinancialFact(
            instrument_id=INSTRUMENTS[0],
            metric=metric,
            report_period=period,
            statement_kind=F0StatementKind.CUMULATIVE,
            value=value * multiplier,
            comparable_scope="scope-a",
            revision_id=f"{metric.value}-{period}",
            announced_at=cutoff - timedelta(days=30),
            source_record_hash=HASH,
        )
        for metric, multiplier in multipliers.items()
        for period, value in periods
    ]
    for metric, current, prior in (
        (F0FinancialMetric.PARENT_EQUITY, 900.0, 800.0),
        (F0FinancialMetric.TOTAL_ASSETS, 2_000.0, 1_800.0),
        (F0FinancialMetric.TOTAL_LIABILITIES, 1_100.0, 1_000.0),
    ):
        for period, value in ((date(2024, 9, 30), current), (date(2023, 9, 30), prior)):
            rows.append(
                F0FinancialFact(
                    instrument_id=INSTRUMENTS[0],
                    metric=metric,
                    report_period=period,
                    statement_kind=F0StatementKind.INSTANT,
                    value=value,
                    comparable_scope="scope-a",
                    revision_id=f"{metric.value}-{period}",
                    announced_at=cutoff - timedelta(days=30),
                    source_record_hash=HASH,
                )
            )
    return tuple(rows)


def _bundle(session_count: int = 260) -> F0InputBundle:
    sessions = _sessions(session_count)
    decisions = _decisions(sessions)
    current_decisions = tuple(
        item for item in decisions if item.decision_date == sessions[-1]
    )
    core_input = _core_input(
        sessions,
        core_universe_content_hash(current_decisions),
    )
    memberships = [
        IndustryMembershipObservation(
            instrument_id=instrument,
            valid_from=sessions[0],
            valid_to=(
                sessions[min(130, len(sessions) - 1) - 1] if instrument == INSTRUMENTS[-1] else None
            ),
            sw_l1=INDUSTRIES[index // 2],
            available_at=datetime.combine(sessions[0], datetime.min.time(), TZ),
            source_record_hash=HASH,
        )
        for index, instrument in enumerate(INSTRUMENTS)
    ]
    memberships.append(
        IndustryMembershipObservation(
            instrument_id=INSTRUMENTS[-1],
            valid_from=sessions[min(130, len(sessions) - 1)],
            sw_l1=INDUSTRIES[1],
            available_at=datetime.combine(
                sessions[min(130, len(sessions) - 1)], datetime.min.time(), TZ
            ),
            source_record_hash=HASH,
        )
    )
    financial_types = {
        1: F0CompanyType.BANK,
        2: F0CompanyType.INSURER,
        3: F0CompanyType.BROKER,
    }
    classifications = tuple(
        F0CompanyClassification(
            instrument_id=instrument,
            company_type=financial_types.get(index, F0CompanyType.CORPORATE),
            effective_from=sessions[0],
            available_at=datetime.combine(sessions[0], datetime.min.time(), TZ),
        )
        for index, instrument in enumerate(INSTRUMENTS)
    )
    return F0InputBundle(
        core_input=core_input,
        common_sessions=sessions,
        universe_decisions=decisions,
        market_bars=_bars(sessions),
        financial_facts=_financial_facts(core_input.cutoff_at),
        dividend_facts=(
            F0DividendFact(
                instrument_id=INSTRUMENTS[0],
                event_id="dividend-2024-final",
                revision_id="dividend-2024-final-r1",
                cash_dividend_per_share=0.5,
                implementation_basis_at=core_input.cutoff_at - timedelta(days=60),
                announced_at=core_input.cutoff_at - timedelta(days=90),
                source_record_hash=HASH,
            ),
        ),
        industry_memberships=tuple(memberships),
        company_classifications=classifications,
    )


def _row(envelope, instrument: str, feature: str):
    return next(
        row
        for row in envelope.rows
        if row.instrument_id == instrument and row.feature_definition_id == feature
    )


def test_f0_registry_is_exact_and_frozen() -> None:
    assert tuple(item.feature_definition_id for item in F0_DEFINITIONS) == (
        ASTRAMIND_F0_FEATURE_ORDER
    )
    assert len(F0_DEFINITIONS) == len(set(ASTRAMIND_F0_FEATURE_ORDER)) == 24
    assert {item.feature_definition_version for item in F0_DEFINITIONS} == {"1.0.0"}
    assert ASTRAMIND_F0.required_definition_registry_hash == F0_DEFINITION_REGISTRY_HASH


def test_f0_ttm_financial_na_and_market_formulas() -> None:
    bundle = _bundle()
    envelope = evaluate_astramind_f0(bundle)
    assert len(envelope.rows) == 6 * 24
    # 2025Q3 + 2024FY - 2024Q3 = 141, divided by 10bn.
    assert _row(envelope, INSTRUMENTS[0], "EP_TTM").value_raw == pytest.approx(
        141 / 10_000_000_000, abs=1e-12, rel=1e-12
    )
    assert _row(envelope, INSTRUMENTS[0], "REVENUE_TTM_YOY").value_raw == pytest.approx(
        141 / 114 - 1, abs=1e-12, rel=1e-12
    )
    bank_ep = _row(envelope, INSTRUMENTS[1], "EP_TTM")
    assert bank_ep.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
    assert _row(envelope, INSTRUMENTS[1], "MOM_60_5").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )
    prices = [
        bar.research_close for bar in bundle.market_bars if bar.instrument_id == INSTRUMENTS[0]
    ]
    expected_momentum = prices[-6] / prices[-61] - 1
    assert _row(envelope, INSTRUMENTS[0], "MOM_60_5").value_raw == pytest.approx(
        expected_momentum, abs=1e-12, rel=1e-12
    )
    assert _row(envelope, INSTRUMENTS[0], "RESIDUAL_REV_20").availability_state == (
        FeatureAvailabilityState.OBSERVED
    )


def test_future_revision_and_market_rows_do_not_change_identity() -> None:
    bundle = _bundle()
    baseline = evaluate_astramind_f0(bundle)
    future_fact = bundle.financial_facts[0].model_copy(
        update={
            "value": 9999.0,
            "revision_id": "future-revision",
            "announced_at": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    future_bar = bundle.market_bars[-1].model_copy(
        update={
            "market_date": bundle.core_input.decision_date + timedelta(days=1),
            "available_at": bundle.core_input.cutoff_at + timedelta(days=1),
            "research_close": 9999.0,
        }
    )
    future_membership = bundle.industry_memberships[0].model_copy(
        update={
            "valid_from": bundle.core_input.decision_date + timedelta(days=1),
            "valid_to": None,
            "sw_l1": "future-industry",
            "available_at": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    future_u0 = next(
        item
        for item in bundle.universe_decisions
        if item.decision_date == bundle.core_input.decision_date
    ).model_copy(
        update={
            "decision_date": bundle.core_input.decision_date + timedelta(days=1),
            "input_cutoff": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    future_dividend = bundle.dividend_facts[0].model_copy(
        update={
            "revision_id": "future-dividend-revision",
            "cash_dividend_per_share": 99.0,
            "implementation_basis_at": bundle.core_input.cutoff_at + timedelta(days=1),
            "announced_at": bundle.core_input.cutoff_at + timedelta(days=1),
        }
    )
    extended = bundle.model_copy(
        update={
            "financial_facts": (*bundle.financial_facts, future_fact),
            "market_bars": (*bundle.market_bars, future_bar),
            "industry_memberships": (
                *bundle.industry_memberships,
                future_membership,
            ),
            "universe_decisions": (*bundle.universe_decisions, future_u0),
            "dividend_facts": (*bundle.dividend_facts, future_dividend),
        }
    )
    assert evaluate_astramind_f0(extended) == baseline


def test_missing_bar_and_zero_amount_fail_closed_without_window_compression() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    missing_day = bundle.common_sessions[-10]
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == target and bar.market_date == missing_day)
    )
    missing_envelope = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": bars}))
    assert (
        _row(missing_envelope, target, "REALIZED_VOL_20").availability_state
        == FeatureAvailabilityState.MISSING
    )

    zero_bars = tuple(
        bar.model_copy(update={"amount_cny": 0.0})
        if bar.instrument_id == target and bar.market_date == missing_day
        else bar
        for bar in bundle.market_bars
    )
    zero_envelope = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": zero_bars}))
    amihud = _row(zero_envelope, target, "AMIHUD_20")
    assert amihud.availability_state == FeatureAvailabilityState.MISSING
    assert amihud.missing_reason_code == "f0_amihud_coverage_incomplete"


def test_date_only_notice_and_missing_industry_fail_closed() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    replaced = []
    for fact in bundle.financial_facts:
        if (
            fact.instrument_id == target
            and fact.metric == F0FinancialMetric.PARENT_NET_PROFIT
            and fact.report_period == date(2024, 9, 30)
        ):
            replaced.append(
                F0FinancialFact(
                    **fact.model_dump(
                        exclude={"announced_at", "announcement_date"},
                    ),
                    announcement_date=bundle.core_input.decision_date,
                )
            )
        else:
            replaced.append(fact)
    memberships = tuple(
        item for item in bundle.industry_memberships if item.instrument_id != target
    )
    envelope = evaluate_astramind_f0(
        bundle.model_copy(
            update={
                "financial_facts": tuple(replaced),
                "industry_memberships": memberships,
            }
        )
    )
    ep = _row(envelope, target, "EP_TTM")
    industry_momentum = _row(envelope, target, "INDUSTRY_REL_MOM_60_5")
    assert ep.availability_state == FeatureAvailabilityState.OBSERVED
    edge = json.loads(GOLDEN_FIXTURE.read_text(encoding="utf-8"))["edge_case_expectations"]
    assert ep.value_raw == pytest.approx(edge["date_only_same_day_uses_older_visible_ep"])
    assert industry_momentum.availability_state == FeatureAvailabilityState.NOT_APPLICABLE
    assert industry_momentum.missing_reason_code == "f0_industry_membership_unavailable"


def test_residual_ols_requires_fifteen_common_valid_observations() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    invalid_days = set(bundle.common_sessions[-10:])
    bars = tuple(
        bar
        for bar in bundle.market_bars
        if not (bar.instrument_id == target and bar.market_date in invalid_days)
    )
    envelope = evaluate_astramind_f0(bundle.model_copy(update={"market_bars": bars}))
    residual = _row(envelope, target, "RESIDUAL_REV_20")
    assert residual.availability_state == FeatureAvailabilityState.MISSING
    assert residual.missing_reason_code == "f0_regression_observations_insufficient"


def test_deleted_common_session_fails_even_when_all_rows_and_u0_delete_it() -> None:
    bundle = _bundle()
    deleted = bundle.common_sessions[-40]
    broken = bundle.model_copy(
        update={
            "common_sessions": tuple(day for day in bundle.common_sessions if day != deleted),
            "market_bars": tuple(bar for bar in bundle.market_bars if bar.market_date != deleted),
            "universe_decisions": tuple(
                item for item in bundle.universe_decisions if item.decision_date != deleted
            ),
        }
    )
    with pytest.raises(ValueError, match="calculation sessions"):
        evaluate_astramind_f0(broken)


def test_missing_ttm_and_negative_growth_base_keep_stable_reasons() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    missing_annual = tuple(
        fact
        for fact in bundle.financial_facts
        if not (
            fact.metric == F0FinancialMetric.REVENUE and fact.report_period == date(2023, 12, 31)
        )
    )
    missing_envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": missing_annual})
    )
    sp = _row(missing_envelope, target, "SP_TTM")
    assert sp.availability_state == FeatureAvailabilityState.MISSING
    assert sp.missing_reason_code == "f0_financial_period_missing"

    negative_prior = tuple(
        fact.model_copy(update={"value": -84.0})
        if fact.metric == F0FinancialMetric.PARENT_NET_PROFIT
        and fact.report_period == date(2023, 9, 30)
        else fact
        for fact in bundle.financial_facts
    )
    growth_envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": negative_prior})
    )
    growth = _row(growth_envelope, target, "NET_PROFIT_TTM_YOY")
    assert growth.availability_state == FeatureAvailabilityState.MISSING
    assert growth.missing_reason_code == "f0_invalid_growth_base"
