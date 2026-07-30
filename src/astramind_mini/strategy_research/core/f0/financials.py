"""The thirteen point-in-time astramind-f0-v1 financial formulas."""

from __future__ import annotations

import math

from .financial_records import (
    FinancialValue,
    average_stock_value,
    company_type,
    dividend_ttm,
    latest_ttm_value,
    market_cap,
    prior_year,
    research_close,
    stock_value,
    ttm_value,
)
from .inputs import F0CompanyType, F0FinancialMetric, F0InputBundle
from .reasons import F0Reason
from .result import FormulaResult, missing, not_applicable, observed

FINANCIAL_FEATURES = (
    "EP_TTM",
    "BP",
    "SP_TTM",
    "DY_TTM",
    "ROE_TTM",
    "ROA_TTM",
    "OPERATING_MARGIN_TTM",
    "OCF_TO_NET_INCOME_TTM",
    "ACCRUALS_TO_ASSETS_TTM",
    "DEBT_TO_ASSETS",
    "REVENUE_TTM_YOY",
    "NET_PROFIT_TTM_YOY",
    "OCF_TTM_YOY",
)


def evaluate_financial_features(
    bundle: F0InputBundle,
    instrument_id: str,
) -> dict[str, FormulaResult]:
    classification = company_type(bundle, instrument_id)
    if classification == F0CompanyType.UNKNOWN:
        return _all_missing(F0Reason.COMPANY_TYPE_UNAVAILABLE)
    if classification != F0CompanyType.CORPORATE:
        return {feature: not_applicable() for feature in FINANCIAL_FEATURES}

    total_market_cap = market_cap(bundle, instrument_id)
    close = research_close(bundle, instrument_id)
    ttm = {
        metric: latest_ttm_value(bundle, instrument_id, metric)
        for metric in (
            F0FinancialMetric.PARENT_NET_PROFIT,
            F0FinancialMetric.NET_PROFIT,
            F0FinancialMetric.REVENUE,
            F0FinancialMetric.OPERATING_PROFIT,
            F0FinancialMetric.OPERATING_CASH_FLOW,
        )
    }
    stock = {
        metric: stock_value(bundle, instrument_id, metric)
        for metric in (
            F0FinancialMetric.PARENT_EQUITY,
            F0FinancialMetric.TOTAL_ASSETS,
            F0FinancialMetric.TOTAL_LIABILITIES,
        )
    }
    avg_equity = average_stock_value(bundle, instrument_id, F0FinancialMetric.PARENT_EQUITY)
    avg_assets = average_stock_value(bundle, instrument_id, F0FinancialMetric.TOTAL_ASSETS)
    prior_ttm = {
        metric: _prior_ttm(bundle, instrument_id, metric, ttm[metric])
        for metric in (
            F0FinancialMetric.REVENUE,
            F0FinancialMetric.PARENT_NET_PROFIT,
            F0FinancialMetric.OPERATING_CASH_FLOW,
        )
    }
    dividend = dividend_ttm(bundle, instrument_id)
    return _formula_results(
        ttm=ttm,
        stock=stock,
        prior_ttm=prior_ttm,
        total_market_cap=total_market_cap,
        close=close,
        avg_equity=avg_equity,
        avg_assets=avg_assets,
        dividend=dividend,
    )


def _formula_results(
    *,
    ttm: dict[F0FinancialMetric, FinancialValue | F0Reason],
    stock: dict[F0FinancialMetric, FinancialValue | F0Reason],
    prior_ttm: dict[F0FinancialMetric, FinancialValue | F0Reason],
    total_market_cap: FinancialValue | F0Reason,
    close: FinancialValue | F0Reason,
    avg_equity: FinancialValue | F0Reason,
    avg_assets: FinancialValue | F0Reason,
    dividend: FinancialValue | F0Reason,
) -> dict[str, FormulaResult]:
    return {
        "EP_TTM": _ratio(ttm[F0FinancialMetric.PARENT_NET_PROFIT], total_market_cap),
        "BP": _ratio(stock[F0FinancialMetric.PARENT_EQUITY], total_market_cap),
        "SP_TTM": _ratio(ttm[F0FinancialMetric.REVENUE], total_market_cap),
        "DY_TTM": _ratio(dividend, close),
        "ROE_TTM": _ratio(
            ttm[F0FinancialMetric.PARENT_NET_PROFIT],
            avg_equity,
            require_scope=True,
            require_period=True,
        ),
        "ROA_TTM": _ratio(
            ttm[F0FinancialMetric.NET_PROFIT],
            avg_assets,
            require_scope=True,
            require_period=True,
        ),
        "OPERATING_MARGIN_TTM": _ratio(
            ttm[F0FinancialMetric.OPERATING_PROFIT],
            ttm[F0FinancialMetric.REVENUE],
            require_scope=True,
            require_period=True,
        ),
        "OCF_TO_NET_INCOME_TTM": _ratio(
            ttm[F0FinancialMetric.OPERATING_CASH_FLOW],
            ttm[F0FinancialMetric.NET_PROFIT],
            require_scope=True,
            require_period=True,
        ),
        "ACCRUALS_TO_ASSETS_TTM": _difference_ratio(
            ttm[F0FinancialMetric.NET_PROFIT],
            ttm[F0FinancialMetric.OPERATING_CASH_FLOW],
            avg_assets,
        ),
        "DEBT_TO_ASSETS": _ratio(
            stock[F0FinancialMetric.TOTAL_LIABILITIES],
            stock[F0FinancialMetric.TOTAL_ASSETS],
            require_scope=True,
            require_period=True,
        ),
        "REVENUE_TTM_YOY": _growth(
            ttm[F0FinancialMetric.REVENUE],
            prior_ttm[F0FinancialMetric.REVENUE],
        ),
        "NET_PROFIT_TTM_YOY": _growth(
            ttm[F0FinancialMetric.PARENT_NET_PROFIT],
            prior_ttm[F0FinancialMetric.PARENT_NET_PROFIT],
        ),
        "OCF_TTM_YOY": _growth(
            ttm[F0FinancialMetric.OPERATING_CASH_FLOW],
            prior_ttm[F0FinancialMetric.OPERATING_CASH_FLOW],
        ),
    }


def _ratio(
    numerator: FinancialValue | F0Reason,
    denominator: FinancialValue | F0Reason,
    *,
    require_scope: bool = False,
    require_period: bool = False,
) -> FormulaResult:
    if isinstance(numerator, F0Reason):
        return missing(numerator)
    if isinstance(denominator, F0Reason):
        return missing(denominator)
    if not math.isfinite(numerator.amount) or not math.isfinite(denominator.amount):
        return missing(F0Reason.NON_FINITE_RESULT)
    if require_scope and numerator.scope != denominator.scope:
        return missing(F0Reason.FINANCIAL_SCOPE_INCOMPARABLE)
    if require_period and numerator.period != denominator.period:
        return missing(F0Reason.FINANCIAL_PERIOD_INCOMPARABLE)
    if denominator.amount == 0:
        return missing(F0Reason.INVALID_DENOMINATOR)
    return observed(numerator.amount / denominator.amount)


def _difference_ratio(
    left: FinancialValue | F0Reason,
    right: FinancialValue | F0Reason,
    denominator: FinancialValue | F0Reason,
) -> FormulaResult:
    if isinstance(left, F0Reason):
        return missing(left)
    if isinstance(right, F0Reason):
        return missing(right)
    if not math.isfinite(left.amount) or not math.isfinite(right.amount):
        return missing(F0Reason.NON_FINITE_RESULT)
    if left.scope != right.scope:
        return missing(F0Reason.FINANCIAL_SCOPE_INCOMPARABLE)
    if left.period != right.period:
        return missing(F0Reason.FINANCIAL_PERIOD_INCOMPARABLE)
    difference = FinancialValue(left.amount - right.amount, left.scope, left.period)
    return _ratio(
        difference,
        denominator,
        require_scope=True,
        require_period=True,
    )


def _growth(
    current: FinancialValue | F0Reason,
    prior: FinancialValue | F0Reason,
) -> FormulaResult:
    if isinstance(current, F0Reason):
        return missing(current)
    if isinstance(prior, F0Reason):
        return missing(prior)
    if not math.isfinite(current.amount) or not math.isfinite(prior.amount):
        return missing(F0Reason.NON_FINITE_RESULT)
    if current.scope != prior.scope:
        return missing(F0Reason.FINANCIAL_SCOPE_INCOMPARABLE)
    if prior.amount == 0 or current.amount * prior.amount <= 0:
        return missing(F0Reason.INVALID_GROWTH_BASE)
    return observed(current.amount / prior.amount - 1)


def _all_missing(reason: F0Reason) -> dict[str, FormulaResult]:
    return {feature: missing(reason) for feature in FINANCIAL_FEATURES}


def _prior_ttm(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
    current: FinancialValue | F0Reason,
) -> FinancialValue | F0Reason:
    if isinstance(current, F0Reason):
        return current
    if current.period is None:
        return F0Reason.FINANCIAL_PERIOD_MISSING
    return ttm_value(bundle, instrument_id, metric, prior_year(current.period))


__all__ = ["FINANCIAL_FEATURES", "evaluate_financial_features"]
