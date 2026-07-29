"""Read-only ETF rotation research contracts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from astramind_mini.contracts.base import ContractModel, Identifier, Version

from .hierarchy import PriceCandle

CandidateState = Literal["eligible", "context_only", "rejected", "stale", "unavailable"]


class EtfRotationCandidate(ContractModel):
    industry_code: Identifier
    industry_name: str
    lifecycle_stage: str
    lifecycle_confidence: str
    etf_code: Identifier | None = None
    etf_name: str | None = None
    mapping_tier: str
    state: CandidateState
    overall_score: float | None = None
    lifecycle_score: float | None = None
    relative_strength_score: float | None = None
    price_structure_score: float | None = None
    liquidity_score: float | None = None
    return_20d: float | None = None
    return_60d: float | None = None
    median_amount_20d_cny: float | None = None
    latest_size_cny: float | None = None
    spread_proxy_bps: float | None = None
    spread_evidence_kind: Literal["corwin_schultz_ohlc_proxy", "unavailable"]
    tracking_error_60d: float | None = None
    tracking_evidence_kind: Literal["sw_l1_exposure_proxy", "unavailable"]
    price_conclusion: str
    rejection_reasons: tuple[str, ...] = ()
    candles: tuple[PriceCandle, ...] = ()
    weekly_candles: tuple[PriceCandle, ...] = ()
    monthly_candles: tuple[PriceCandle, ...] = ()


class EtfFunnel(ContractModel):
    industry_count: int
    exact_mapping_count: int
    foundation_count: int
    evidence_gate_count: int
    eligible_count: int


class EtfTargetWeight(ContractModel):
    industry_code: Identifier
    etf_code: Identifier
    target_weight: float
    reason: str


class EtfTargetDraft(ContractModel):
    status: Literal["draft", "cash_only", "blocked"]
    weights: tuple[EtfTargetWeight, ...] = ()
    cash_weight: float
    max_gross_weight: float
    current_weights_observed: Literal[False] = False
    portfolio_target_created: Literal[False] = False
    order_plan_created: Literal[False] = False
    known_gaps: tuple[str, ...] = ()


class EtfReplaySummary(ContractModel):
    status: Literal["blocked", "candidate_frozen", "diagnostic"]
    evidence_label: str
    start_date: date | None = None
    end_date: date | None = None
    decision_count: int = 0
    total_return: float | None = None
    max_drawdown: float | None = None
    turnover: float | None = None
    estimated_cost_cny: float | None = None
    next_open_execution: Literal[True] = True
    initial_research_cash_cny: float = 50_000.0
    commission_rate: float = 0.00005
    minimum_commission_cny: float = 5.0
    slippage_bps_per_side: float = 20.0
    stamp_duty_rate: float = 0.0
    promotion_evidence_eligible: Literal[False] = False
    known_gaps: tuple[str, ...] = ()


class EtfRotationProjection(ContractModel):
    status: Literal["ready", "stale", "blocked"]
    rotation_snapshot_id: Identifier
    data_snapshot_id: Identifier
    as_of: datetime
    evidence_cutoff: date | None = None
    strategy_version: Version
    mapping_version: Version
    spread_proxy_threshold_bps: float
    tracking_proxy_threshold: float
    funnel: EtfFunnel
    candidates: tuple[EtfRotationCandidate, ...] = ()
    target_draft: EtfTargetDraft
    replay: EtfReplaySummary
    selected_etf_code: Identifier | None = None
    known_gaps: tuple[str, ...] = ()
    broker_actions_allowed: Literal[False] = False


__all__ = [
    "CandidateState",
    "EtfFunnel",
    "EtfReplaySummary",
    "EtfRotationCandidate",
    "EtfRotationProjection",
    "EtfTargetDraft",
    "EtfTargetWeight",
]
