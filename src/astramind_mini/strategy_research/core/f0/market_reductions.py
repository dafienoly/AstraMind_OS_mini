"""Frozen cross-section, compounding, and OLS reductions for F0."""

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import date
from statistics import fmean

import numpy as np

from ..semantics import point_in_time_industry_level, select_point_in_time_industry
from .computation_semantics import F0_MARKET_OPERATOR_SEMANTICS as _SEMANTICS
from .inputs import F0InputBundle, F0MarketBar, session_cutoff
from .market_series import close_value, simple_return
from .reasons import F0Reason


def industry_at(bundle: F0InputBundle, instrument_id: str, day: date) -> str | None:
    membership = select_point_in_time_industry(
        bundle.industry_memberships,
        instrument_id=instrument_id,
        decision_date=day,
        cutoff_at=session_cutoff(day, bundle.core_input.cutoff_at),
    )
    return point_in_time_industry_level(membership, level="sw_l1")


def cross_section_return(
    bundle: F0InputBundle,
    bars: dict[tuple[str, date], F0MarketBar],
    previous_day: date,
    day: date,
    target_industry: str | None = None,
) -> float | F0Reason:
    _validate_cross_section_semantics()
    members = sorted(
        item.instrument_id
        for item in bundle.universe_decisions
        if item.decision_date == day
        and item.research_member
        and item.input_cutoff <= session_cutoff(day, bundle.core_input.cutoff_at)
        and (
            target_industry is None
            or industry_at(bundle, item.instrument_id, day) == target_industry
        )
    )
    if not members:
        return F0Reason.INDUSTRY_RETURN_UNAVAILABLE
    returns: list[float] = []
    for member in members:
        previous = close_value(bars, member, previous_day)
        current = close_value(bars, member, day)
        if previous is None or current is None:
            return F0Reason.INDUSTRY_RETURN_UNAVAILABLE
        if not math.isfinite(previous) or not math.isfinite(current):
            return F0Reason.NON_FINITE_RESULT
        returns.append(simple_return(previous, current))
    return fmean(returns)


def industry_relative_period(
    sessions: Sequence[date],
    old_offset: int,
    new_offset: int,
) -> tuple[date, ...] | None:
    if _SEMANTICS.window_endpoint_policy != (
        "include_close_at_t_minus_old_offset_and_t_minus_new_offset;"
        "daily_returns_are_adjacent_pairs_between_endpoints"
    ):
        raise RuntimeError("unsupported F0 window endpoint policy")
    if len(sessions) < old_offset + 1:
        return None
    period = tuple(sessions[-old_offset - 1 : -new_offset])
    if len(period) - 1 != _SEMANTICS.industry_relative_return_observations:
        raise RuntimeError("F0 industry-relative window semantics are inconsistent")
    return period


def compound_returns(returns: Sequence[float]) -> float:
    if (
        _SEMANTICS.industry_compounding_operator
        != "geometric_product_one_plus_return_minus_one"
    ):
        raise RuntimeError("unsupported F0 industry compounding operator")
    return math.prod(1 + value for value in returns) - 1


def incomplete_ols_rows_are_dropped() -> bool:
    if (
        _SEMANTICS.ols_row_coverage_policy
        != "drop_incomplete_row_then_apply_minimum_observations"
    ):
        raise RuntimeError("unsupported F0 OLS row coverage policy")
    return True


def ols_residual_reversal(
    rows: Sequence[tuple[float, float, float]],
) -> float | F0Reason:
    if len(rows) < _SEMANTICS.residual_minimum_observations:
        return F0Reason.REGRESSION_OBSERVATIONS_INSUFFICIENT
    if _SEMANTICS.ols_solver != "numpy_lstsq":
        raise RuntimeError("unsupported F0 OLS solver")
    if _SEMANTICS.ols_design_columns != (
        "intercept",
        "u0_equal_weight_simple_return",
        "sw_l1_equal_weight_simple_return",
    ):
        raise RuntimeError("unsupported F0 OLS design")
    y = np.asarray([row[0] for row in rows], dtype=float)
    x = np.column_stack(
        (
            np.ones(len(rows)),
            np.asarray([row[1] for row in rows]),
            np.asarray([row[2] for row in rows]),
        )
    )
    coefficients, _, rank, _ = np.linalg.lstsq(x, y, rcond=_SEMANTICS.ols_rcond)
    if _SEMANTICS.ols_rank_policy != (
        "reported_design_rank_must_meet_required_design_rank"
    ):
        raise RuntimeError("unsupported F0 OLS rank policy")
    if rank < _SEMANTICS.residual_required_design_rank:
        if _SEMANTICS.ols_singular_policy != "missing_f0_regression_singular":
            raise RuntimeError("unsupported F0 OLS singular policy")
        return F0Reason.REGRESSION_SINGULAR
    if (
        _SEMANTICS.ols_residual_reduction
        != "negative_sum_in_chronological_session_order"
    ):
        raise RuntimeError("unsupported F0 OLS residual reduction")
    return -float(np.sum(y - x @ coefficients))


def _validate_cross_section_semantics() -> None:
    required = (
        _SEMANTICS.cross_section_reducer == "equal_weight_arithmetic_mean"
        and _SEMANTICS.cross_section_tie_policy
        == "no_ranking;equal_values_keep_equal_weight"
        and _SEMANTICS.cross_section_coverage_policy
        == "all_eligible_members_require_finite_price_pair"
        and _SEMANTICS.missing_peer_bar_policy == "cross_section_unavailable"
    )
    if not required:
        raise RuntimeError("unsupported F0 cross-section semantics")


__all__ = [
    "compound_returns",
    "cross_section_return",
    "incomplete_ols_rows_are_dropped",
    "industry_at",
    "industry_relative_period",
    "ols_residual_reversal",
]
