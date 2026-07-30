"""Frozen operator semantics that participate in the F0 computation identity."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class F0FinancialComputationSemantics:
    availability: str
    financial_revision_identity: str
    dividend_revision_identity: str
    revision_selection: str
    equal_availability_policy: str
    classification_identity: str
    classification_interval_policy: str
    classification_selection: str
    classification_equal_key_policy: str
    cumulative_fields: tuple[str, ...]
    fiscal_year_end_month_day: tuple[int, int]
    prior_year_offset: int
    ttm: str
    instant_fields: tuple[str, ...]
    instant: str
    average_stock_observations: int
    average_stock: str
    flow_stock_period_compatibility: str
    growth: str
    cross_field_comparability: str
    dividend_trailing_calendar_years: int
    dividend: str
    financial_company_applicability: str
    numeric_failure_policy: str


@dataclass(frozen=True)
class F0MarketOperatorSemantics:
    market_bar_selection: str
    market_bar_equal_time_policy: str
    simple_return_operator: str
    momentum_windows: tuple[tuple[str, int, int], ...]
    reversal_window_sessions: int
    industry_relative_momentum_window: tuple[int, int]
    industry_relative_return_observations: int
    window_endpoint_policy: str
    cross_section_reducer: str
    cross_section_tie_policy: str
    cross_section_coverage_policy: str
    missing_peer_bar_policy: str
    industry_compounding_operator: str
    residual_window_returns: int
    residual_minimum_observations: int
    residual_required_design_rank: int
    ols_row_coverage_policy: str
    ols_solver: str
    ols_rcond: float | None
    ols_design_columns: tuple[str, ...]
    ols_rank_policy: str
    ols_singular_policy: str
    ols_residual_reduction: str
    realized_volatility_window_returns: int
    downside_volatility_window_returns: int
    annualization_sessions: int
    liquidity_window_sessions: int
    amihud_scale: float
    price_and_return_semantics: str
    raw_field_semantics: str
    common_session_coverage: str
    industry_return_coverage: str
    residual_regression: str
    historical_cross_section: str
    applicability_gate_priority: str
    availability_states: str
    numeric_failure_policy: str


F0_FINANCIAL_COMPUTATION_SEMANTICS = F0FinancialComputationSemantics(
    availability=(
        "announced_at_or_next_common_session_close_for_date_only;"
        "latest_visible_revision_only"
    ),
    financial_revision_identity=(
        "instrument_id+metric+report_period+statement_kind+revision_id"
    ),
    dividend_revision_identity="instrument_id+event_id+revision_id",
    revision_selection="maximum_authoritative_availability_time_only",
    equal_availability_policy=(
        "identical_calculation_payloads_merge;different_payloads_fail_closed;"
        "revision_id_never_orders_revisions"
    ),
    classification_identity="instrument_id+effective_from+available_at",
    classification_interval_policy="decision_date_in_closed_effective_interval",
    classification_selection="maximum_effective_from_then_maximum_available_at",
    classification_equal_key_policy=(
        "identical_record_deduplicates_otherwise_fail_closed"
    ),
    cumulative_fields=(
        "parent_net_profit",
        "net_profit",
        "revenue",
        "operating_profit",
        "operating_cash_flow",
    ),
    fiscal_year_end_month_day=(12, 31),
    prior_year_offset=1,
    ttm=(
        "each_metric_independently_selects_its_latest_visible_cumulative_period;"
        "current_ytd + prior_fy - prior_year_same_period_ytd;no_annualization;"
        "latest_metric_period_missing_support_fails_closed"
    ),
    instant_fields=("parent_equity", "total_assets", "total_liabilities"),
    instant="each_metric_independently_selects_latest_visible_period",
    average_stock_observations=2,
    average_stock=(
        "latest_visible_instant_end + prior_year_same_period_begin;"
        "matching_comparable_scope_required"
    ),
    flow_stock_period_compatibility=(
        "ttm_report_period_must_exactly_equal_average_stock_end_period"
    ),
    growth="current_and_prior_ttm_same_sign;abs(prior)>0",
    cross_field_comparability=(
        "financial_scopes_must_match;flow_ratios_and_instant_ratios_require_matching_periods"
    ),
    dividend_trailing_calendar_years=1,
    dividend=(
        "stable_event_id_and_revision_id;latest_visible_revision_per_event_only;"
        "public_and_implementation_based_cash_dividend_per_share_trailing_12_calendar_months"
    ),
    financial_company_applicability="bank_insurer_broker_not_applicable",
    numeric_failure_policy="zero_denominator_or_non_finite_result_is_missing;no_epsilon",
)

F0_MARKET_OPERATOR_SEMANTICS = F0MarketOperatorSemantics(
    market_bar_selection="maximum_authoritative_available_at",
    market_bar_equal_time_policy="identical_record_deduplicates_otherwise_fail_closed",
    simple_return_operator="current_close_div_previous_close_minus_one",
    momentum_windows=(
        ("MOM_20_5", 20, 5),
        ("MOM_60_5", 60, 5),
        ("MOM_120_20", 120, 20),
    ),
    reversal_window_sessions=5,
    industry_relative_momentum_window=(60, 5),
    industry_relative_return_observations=55,
    window_endpoint_policy=(
        "include_close_at_t_minus_old_offset_and_t_minus_new_offset;"
        "daily_returns_are_adjacent_pairs_between_endpoints"
    ),
    cross_section_reducer="equal_weight_arithmetic_mean",
    cross_section_tie_policy="no_ranking;equal_values_keep_equal_weight",
    cross_section_coverage_policy="all_eligible_members_require_finite_price_pair",
    missing_peer_bar_policy="cross_section_unavailable",
    industry_compounding_operator="geometric_product_one_plus_return_minus_one",
    residual_window_returns=20,
    residual_minimum_observations=15,
    residual_required_design_rank=3,
    ols_row_coverage_policy="drop_incomplete_row_then_apply_minimum_observations",
    ols_solver="numpy_lstsq",
    ols_rcond=None,
    ols_design_columns=(
        "intercept",
        "u0_equal_weight_simple_return",
        "sw_l1_equal_weight_simple_return",
    ),
    ols_rank_policy="reported_design_rank_must_meet_required_design_rank",
    ols_singular_policy="missing_f0_regression_singular",
    ols_residual_reduction="negative_sum_in_chronological_session_order",
    realized_volatility_window_returns=20,
    downside_volatility_window_returns=60,
    annualization_sessions=252,
    liquidity_window_sessions=20,
    amihud_scale=1e8,
    price_and_return_semantics=(
        "continuous_research_close_gt_zero;simple_returns_except_realized_vol_uses_log_returns;"
        "sample_std_ddof_1"
    ),
    raw_field_semantics=(
        "amount_cny_and_turnover_rate_are_unadjusted_point_in_time_values;"
        "market_cap_is_unadjusted_point_in_time_value;amihud_requires_amount_strictly_gt_zero"
    ),
    common_session_coverage=(
        "windows_index_complete_frozen_common_sessions;missing_bar_or_required_field_fails_closed;"
        "suspension_price_limit_and_corporate_action_do_not_compress_windows"
    ),
    industry_return_coverage=(
        "industry_relative_momentum_requires_complete_finite_eligible_peer_pairs_each_session;"
        "residual_ols_drops_incomplete_rows_then_applies_minimum"
    ),
    residual_regression=(
        "intercept_plus_u0_equal_weight_simple_return_plus_sw_l1_equal_weight_simple_return;"
        "numpy_lstsq_rcond_none;negative_sum_of_residuals"
    ),
    historical_cross_section=(
        "daily_point_in_time_u0_research_members_and_sw_l1_membership;"
        "u0_member_input_cutoff_must_be_visible_at_session_cutoff"
    ),
    applicability_gate_priority=(
        "current_sw_l1_unavailable_is_not_applicable_before_stock_window_or_regression_missing"
    ),
    availability_states=(
        "observed_only_for_complete_finite_result;missing_for_data_or_numeric_failure;"
        "not_applicable_only_for_declared_industry_gate"
    ),
    numeric_failure_policy="non_finite_is_missing;zero_amount_amihud_is_missing;no_epsilon",
)


__all__ = [
    "F0_FINANCIAL_COMPUTATION_SEMANTICS",
    "F0_MARKET_OPERATOR_SEMANTICS",
    "F0FinancialComputationSemantics",
    "F0MarketOperatorSemantics",
]
