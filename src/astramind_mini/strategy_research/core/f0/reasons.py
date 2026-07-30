"""Stable F0 availability reason codes."""

from enum import StrEnum


class F0Reason(StrEnum):
    FINANCIAL_NOT_APPLICABLE = "f0_financial_not_applicable"
    COMPANY_TYPE_UNAVAILABLE = "f0_company_type_unavailable"
    FINANCIAL_INPUT_MISSING = "f0_financial_input_missing"
    FINANCIAL_PERIOD_MISSING = "f0_financial_period_missing"
    FINANCIAL_PERIOD_INCOMPARABLE = "f0_financial_period_incomparable"
    FINANCIAL_SCOPE_INCOMPARABLE = "f0_financial_scope_incomparable"
    INVALID_DENOMINATOR = "f0_invalid_denominator"
    INVALID_GROWTH_BASE = "f0_invalid_growth_base"
    DIVIDEND_INPUT_MISSING = "f0_dividend_input_missing"
    MARKET_INPUT_MISSING = "f0_market_input_missing"
    COMMON_SESSION_WINDOW_INCOMPLETE = "f0_common_session_window_incomplete"
    INDUSTRY_MEMBERSHIP_UNAVAILABLE = "f0_industry_membership_unavailable"
    INDUSTRY_RETURN_UNAVAILABLE = "f0_industry_return_unavailable"
    U0_RETURN_UNAVAILABLE = "f0_u0_return_unavailable"
    REGRESSION_OBSERVATIONS_INSUFFICIENT = "f0_regression_observations_insufficient"
    REGRESSION_SINGULAR = "f0_regression_singular"
    AMIHUD_COVERAGE_INCOMPLETE = "f0_amihud_coverage_incomplete"
    NON_FINITE_RESULT = "f0_non_finite_result"


__all__ = ["F0Reason"]
