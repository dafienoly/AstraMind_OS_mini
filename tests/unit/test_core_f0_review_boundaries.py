from dataclasses import replace
from datetime import date, timedelta

import pytest

from astramind_mini.strategy_research.core import (
    CoreRawFeatureRowDraft,
    build_core_raw_feature_envelope,
)
from astramind_mini.strategy_research.core.f0 import (
    F0_DEFINITION_REGISTRY_HASH,
    F0_DEFINITIONS,
    F0_FULL_DEFINITION_MANIFEST_HASH,
    F0FinancialMetric,
    F0StatementKind,
    evaluate_astramind_f0,
    full_definition_manifest_hash,
    validate_f0_definition_manifest,
)
from astramind_mini.strategy_research.core.feature_values import (
    FeatureAvailabilityState,
)
from astramind_mini.strategy_research.core.packages import (
    ASTRAMIND_F0,
    ASTRAMIND_F0_FEATURE_ORDER,
)
from tests.unit.test_core_f0_unit import INSTRUMENTS, _bundle, _row

EXPECTED_REQ_SECTION_SIX = (
    ("EP_TTM", "value", "positive", "parent_net_profit_ttm / total_market_cap"),
    ("BP", "value", "positive", "parent_equity / total_market_cap"),
    ("SP_TTM", "value", "positive", "revenue_ttm / total_market_cap"),
    (
        "DY_TTM",
        "value",
        "positive",
        "cash_dividend_per_share_12m / research_close",
    ),
    (
        "ROE_TTM",
        "profitability",
        "positive",
        "parent_net_profit_ttm / average_parent_equity",
    ),
    (
        "ROA_TTM",
        "profitability",
        "positive",
        "net_profit_ttm / average_total_assets",
    ),
    (
        "OPERATING_MARGIN_TTM",
        "profitability",
        "positive",
        "operating_profit_ttm / revenue_ttm",
    ),
    (
        "OCF_TO_NET_INCOME_TTM",
        "quality",
        "positive",
        "operating_cash_flow_ttm / net_profit_ttm",
    ),
    (
        "ACCRUALS_TO_ASSETS_TTM",
        "quality",
        "negative",
        "(net_profit_ttm - operating_cash_flow_ttm) / average_total_assets",
    ),
    (
        "DEBT_TO_ASSETS",
        "quality",
        "negative",
        "total_liabilities / total_assets",
    ),
    (
        "REVENUE_TTM_YOY",
        "growth",
        "positive",
        "revenue_ttm / prior_year_revenue_ttm - 1",
    ),
    (
        "NET_PROFIT_TTM_YOY",
        "growth",
        "positive",
        "parent_net_profit_ttm / prior_year_parent_net_profit_ttm - 1",
    ),
    (
        "OCF_TTM_YOY",
        "growth",
        "positive",
        "operating_cash_flow_ttm / prior_year_operating_cash_flow_ttm - 1",
    ),
    ("MOM_20_5", "momentum", "positive", "close[T-5] / close[T-20] - 1"),
    ("MOM_60_5", "momentum", "positive", "close[T-5] / close[T-60] - 1"),
    (
        "MOM_120_20",
        "momentum",
        "positive",
        "close[T-20] / close[T-120] - 1",
    ),
    (
        "INDUSTRY_REL_MOM_60_5",
        "momentum",
        "positive",
        "MOM_60_5 - contemporaneous_SW_L1_equal_weight_return",
    ),
    ("REV_5", "reversal", "positive", "-(close[T] / close[T-5] - 1)"),
    (
        "RESIDUAL_REV_20",
        "reversal",
        "positive",
        "-sum(OLS residuals over 20 sessions)",
    ),
    (
        "REALIZED_VOL_20",
        "low_volatility",
        "negative",
        "sqrt(252) * sample_std(log_return, ddof=1)",
    ),
    (
        "DOWNSIDE_VOL_60",
        "low_volatility",
        "negative",
        "sqrt(252 * mean(min(simple_return, 0)^2))",
    ),
    (
        "LOG_MEDIAN_AMOUNT_20",
        "liquidity",
        "positive",
        "log(1 + median(raw_amount, 20))",
    ),
    (
        "TURNOVER_MEAN_20",
        "liquidity",
        "positive",
        "mean(raw_turnover_rate, 20)",
    ),
    (
        "AMIHUD_20",
        "liquidity",
        "negative",
        "log(1 + 1e8 * mean(abs(simple_return) / raw_amount, 20))",
    ),
)


def test_definition_formula_family_and_direction_match_req_section_six() -> None:
    actual = tuple(
        (
            item.feature_definition_id,
            item.family,
            item.direction,
            item.formula,
        )
        for item in F0_DEFINITIONS
    )
    assert actual == EXPECTED_REQ_SECTION_SIX


def test_instant_metrics_select_latest_visible_period_independently() -> None:
    bundle = _bundle()
    target = INSTRUMENTS[0]
    instant = []
    for fact in bundle.financial_facts:
        if fact.statement_kind != F0StatementKind.INSTANT:
            instant.append(fact)
            continue
        current = fact.report_period == date(2024, 9, 30)
        instant.append(
            fact.model_copy(
                update={
                    "report_period": date(2024 if current else 2023, 6, 30),
                    "revision_id": f"q2-{fact.revision_id}",
                    "comparable_scope": (
                        "scope-b"
                        if fact.metric == F0FinancialMetric.TOTAL_ASSETS and not current
                        else "scope-a"
                    ),
                }
            )
        )
    equity_current = next(
        fact
        for fact in instant
        if fact.metric == F0FinancialMetric.PARENT_EQUITY
        and fact.report_period == date(2024, 6, 30)
    )
    instant.extend(
        (
            equity_current.model_copy(
                update={
                    "value": 920.0,
                    "revision_id": "visible-q2-revision",
                    "announced_at": bundle.core_input.cutoff_at - timedelta(days=5),
                }
            ),
            equity_current.model_copy(
                update={
                    "value": 999.0,
                    "revision_id": "future-q2-revision",
                    "announced_at": bundle.core_input.cutoff_at + timedelta(days=1),
                }
            ),
        )
    )
    envelope = evaluate_astramind_f0(bundle.model_copy(update={"financial_facts": tuple(instant)}))
    assert _row(envelope, target, "BP").value_raw == pytest.approx(920 / 1e10)
    assert _row(envelope, target, "DEBT_TO_ASSETS").value_raw == pytest.approx(0.55)
    roe = _row(envelope, target, "ROE_TTM")
    assert roe.availability_state == FeatureAvailabilityState.MISSING
    assert roe.missing_reason_code == "f0_financial_period_incomparable"
    roa = _row(envelope, target, "ROA_TTM")
    assert roa.availability_state == FeatureAvailabilityState.MISSING
    assert roa.missing_reason_code == "f0_financial_scope_incomparable"

    missing_prior = tuple(
        fact
        for fact in instant
        if not (
            fact.metric == F0FinancialMetric.PARENT_EQUITY
            and fact.report_period == date(2023, 6, 30)
        )
    )
    missing_envelope = evaluate_astramind_f0(
        bundle.model_copy(update={"financial_facts": missing_prior})
    )
    roe = _row(missing_envelope, target, "ROE_TTM")
    assert roe.availability_state == FeatureAvailabilityState.MISSING
    assert roe.missing_reason_code == "f0_financial_period_missing"


def test_full_definition_manifest_rejects_formula_and_direction_drift() -> None:
    assert validate_f0_definition_manifest(F0_DEFINITIONS) == (F0_FULL_DEFINITION_MANIFEST_HASH)
    for changed in (
        replace(F0_DEFINITIONS[0], formula="tampered_formula"),
        replace(F0_DEFINITIONS[0], direction="negative"),
    ):
        tampered = (changed, *F0_DEFINITIONS[1:])
        assert full_definition_manifest_hash(tampered) != (F0_FULL_DEFINITION_MANIFEST_HASH)
        with pytest.raises(ValueError, match="full definition manifest drifted"):
            validate_f0_definition_manifest(tampered)


def test_legacy_definition_hash_cannot_impersonate_f0_computation_lineage() -> None:
    bundle = _bundle()
    canonical = evaluate_astramind_f0(bundle)
    drafts = tuple(
        CoreRawFeatureRowDraft(
            instrument_id=row.instrument_id,
            decision_time=row.decision_time,
            feature_definition_id=row.feature_definition_id,
            feature_definition_version=row.feature_definition_version,
            value_raw=row.value_raw,
            availability_state=row.availability_state,
            missing_reason_code=row.missing_reason_code,
        )
        for row in canonical.rows
    )
    legacy = build_core_raw_feature_envelope(
        core_input=bundle.core_input,
        package_spec=ASTRAMIND_F0,
        computation_manifest_hash=F0_DEFINITION_REGISTRY_HASH,
        calculation_sessions=bundle.common_sessions,
        feature_order=ASTRAMIND_F0_FEATURE_ORDER,
        rows=drafts,
    )
    assert canonical.manifest.computation_manifest_hash == (F0_FULL_DEFINITION_MANIFEST_HASH)
    assert legacy.manifest.computation_manifest_hash == F0_DEFINITION_REGISTRY_HASH
    assert legacy.feature_snapshot.content_hash != canonical.feature_snapshot.content_hash


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
