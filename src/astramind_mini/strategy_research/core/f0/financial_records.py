"""Point-in-time record selection and TTM construction for F0."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from ..semantics import financial_available_at
from .classification_records import select_company_type
from .computation_semantics import F0_FINANCIAL_COMPUTATION_SEMANTICS as _SEMANTICS
from .inputs import (
    F0CompanyType,
    F0DividendFact,
    F0FinancialFact,
    F0FinancialMetric,
    F0InputBundle,
    F0StatementKind,
    canonical_dividend_facts,
    canonical_financial_facts,
)
from .market_series import bar_index
from .reasons import F0Reason


@dataclass(frozen=True)
class FinancialValue:
    amount: float
    scope: str
    period: date | None


@dataclass(frozen=True)
class SelectedFinancialRecord:
    report_period: date
    value: float
    comparable_scope: str


def company_type(bundle: F0InputBundle, instrument_id: str) -> F0CompanyType:
    return select_company_type(bundle, instrument_id)


def latest_ttm_value(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
) -> FinancialValue | F0Reason:
    """Build the metric's own latest visible TTM without coupling fields."""
    facts = _visible_facts(bundle, instrument_id, metric, F0StatementKind.CUMULATIVE)
    if not facts:
        return F0Reason.FINANCIAL_INPUT_MISSING
    return ttm_value(bundle, instrument_id, metric, facts[-1].report_period)


def ttm_value(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
    period: date,
) -> FinancialValue | F0Reason:
    current = _fact_at(bundle, instrument_id, metric, F0StatementKind.CUMULATIVE, period)
    if current is None:
        return F0Reason.FINANCIAL_INPUT_MISSING
    if (period.month, period.day) == _SEMANTICS.fiscal_year_end_month_day:
        return FinancialValue(current.value, current.comparable_scope, period)
    prior_same = _fact_at(
        bundle,
        instrument_id,
        metric,
        F0StatementKind.CUMULATIVE,
        prior_year(period),
    )
    prior_annual = _fact_at(
        bundle,
        instrument_id,
        metric,
        F0StatementKind.CUMULATIVE,
        date(
            period.year - _SEMANTICS.prior_year_offset,
            *_SEMANTICS.fiscal_year_end_month_day,
        ),
    )
    if prior_same is None or prior_annual is None:
        return F0Reason.FINANCIAL_PERIOD_MISSING
    scopes = {
        current.comparable_scope,
        prior_same.comparable_scope,
        prior_annual.comparable_scope,
    }
    if len(scopes) != 1:
        return F0Reason.FINANCIAL_SCOPE_INCOMPARABLE
    return FinancialValue(
        current.value + prior_annual.value - prior_same.value,
        current.comparable_scope,
        period,
    )


def stock_value(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
) -> FinancialValue | F0Reason:
    facts = _visible_facts(bundle, instrument_id, metric, F0StatementKind.INSTANT)
    fact = facts[-1] if facts else None
    if fact is None:
        return F0Reason.FINANCIAL_INPUT_MISSING
    return FinancialValue(fact.value, fact.comparable_scope, fact.report_period)


def average_stock_value(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
) -> FinancialValue | F0Reason:
    facts = _visible_facts(bundle, instrument_id, metric, F0StatementKind.INSTANT)
    if not facts:
        return F0Reason.FINANCIAL_INPUT_MISSING
    current = facts[-1]
    prior = next(
        (item for item in facts if item.report_period == prior_year(current.report_period)),
        None,
    )
    if prior is None:
        return F0Reason.FINANCIAL_PERIOD_MISSING
    if current.comparable_scope != prior.comparable_scope:
        return F0Reason.FINANCIAL_SCOPE_INCOMPARABLE
    return FinancialValue(
        (current.value + prior.value) / _SEMANTICS.average_stock_observations,
        current.comparable_scope,
        current.report_period,
    )


def market_cap(bundle: F0InputBundle, instrument_id: str) -> FinancialValue | F0Reason:
    return _market_value(bundle, instrument_id, "raw_total_market_cap_cny")


def research_close(bundle: F0InputBundle, instrument_id: str) -> FinancialValue | F0Reason:
    return _market_value(bundle, instrument_id, "research_close")


def dividend_ttm(bundle: F0InputBundle, instrument_id: str) -> FinancialValue | F0Reason:
    cutoff = bundle.core_input.cutoff_at
    earliest = _prior_year_datetime(cutoff)
    visible_by_event: dict[str, list[tuple[datetime, F0DividendFact]]] = {}
    for fact in canonical_dividend_facts(bundle.dividend_facts):
        available = financial_available_at(
            fact.as_core_observation(),
            common_sessions=bundle.common_sessions,
        )
        if fact.instrument_id != instrument_id or available is None or available > cutoff:
            continue
        visible_by_event.setdefault(fact.event_id, []).append((available, fact))
    values: list[float] = []
    for revisions in visible_by_event.values():
        latest_available = max(item[0] for item in revisions)
        latest = [fact for available, fact in revisions if available == latest_available]
        payloads = {
            (fact.cash_dividend_per_share, fact.implementation_basis_at) for fact in latest
        }
        if len(payloads) != 1:
            raise ValueError("dividend revisions conflict at the latest availability time")
        amount, implementation_basis_at = next(iter(payloads))
        if earliest < implementation_basis_at <= cutoff:
            values.append(amount)
    if not values:
        return F0Reason.DIVIDEND_INPUT_MISSING
    return FinancialValue(sum(values), "dividend", bundle.core_input.decision_date)


def prior_year(period: date) -> date:
    try:
        return period.replace(year=period.year - _SEMANTICS.prior_year_offset)
    except ValueError:
        return period.replace(
            year=period.year - _SEMANTICS.prior_year_offset,
            day=28,
        )


def _prior_year_datetime(value: datetime) -> datetime:
    try:
        return value.replace(
            year=value.year - _SEMANTICS.dividend_trailing_calendar_years
        )
    except ValueError:
        return value.replace(
            year=value.year - _SEMANTICS.dividend_trailing_calendar_years,
            day=28,
        )


def _visible_facts(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
    kind: F0StatementKind,
) -> tuple[SelectedFinancialRecord, ...]:
    visible_by_period: dict[date, list[tuple[datetime, F0FinancialFact]]] = {}
    for fact in canonical_financial_facts(bundle.financial_facts):
        if (
            fact.instrument_id != instrument_id
            or fact.metric != metric
            or fact.statement_kind != kind
            or fact.report_period > bundle.core_input.decision_date
        ):
            continue
        available = financial_available_at(
            fact.as_core_observation(),
            common_sessions=bundle.common_sessions,
        )
        if available is None or available > bundle.core_input.cutoff_at:
            continue
        visible_by_period.setdefault(fact.report_period, []).append((available, fact))
    selected: list[SelectedFinancialRecord] = []
    for period, revisions in sorted(visible_by_period.items()):
        latest_available = max(item[0] for item in revisions)
        latest = [fact for available, fact in revisions if available == latest_available]
        payloads = {(fact.value, fact.comparable_scope) for fact in latest}
        if len(payloads) != 1:
            raise ValueError("financial revisions conflict at the latest availability time")
        value, comparable_scope = next(iter(payloads))
        selected.append(SelectedFinancialRecord(period, value, comparable_scope))
    return tuple(selected)


def _fact_at(
    bundle: F0InputBundle,
    instrument_id: str,
    metric: F0FinancialMetric,
    kind: F0StatementKind,
    period: date,
) -> SelectedFinancialRecord | None:
    return next(
        (
            item
            for item in _visible_facts(bundle, instrument_id, metric, kind)
            if item.report_period == period
        ),
        None,
    )


def _market_value(
    bundle: F0InputBundle,
    instrument_id: str,
    field: str,
) -> FinancialValue | F0Reason:
    bar = bar_index(bundle).get((instrument_id, bundle.core_input.decision_date))
    if bar is None:
        return F0Reason.MARKET_INPUT_MISSING
    value = getattr(bar, field)
    if value is None:
        return F0Reason.MARKET_INPUT_MISSING
    return FinancialValue(float(value), "market", bundle.core_input.decision_date)


__all__ = [
    "FinancialValue",
    "average_stock_value",
    "company_type",
    "dividend_ttm",
    "latest_ttm_value",
    "market_cap",
    "prior_year",
    "research_close",
    "stock_value",
    "ttm_value",
]
