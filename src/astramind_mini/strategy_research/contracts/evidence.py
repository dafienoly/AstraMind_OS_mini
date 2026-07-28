"""Strict research-evidence and manual-promotion records."""

from __future__ import annotations

from datetime import date
from typing import Literal

from astramind_mini.contracts.base import (
    AwareDatetime,
    ContentHash,
    ContractModel,
    Identifier,
)


class EvidenceMetrics(ContractModel):
    total_return: float
    annualized_return: float
    annualized_volatility: float
    sharpe: float
    sortino: float
    max_drawdown: float
    calmar: float
    win_rate: float
    payoff_ratio: float
    turnover: float
    closed_trades: int
    rejected_orders: int


class YearEvidence(ContractModel):
    year: int
    start_equity_cny: float
    end_equity_cny: float
    return_rate: float
    closed_trades: int


class FailureEvidence(ContractModel):
    reason: Identifier
    count: int


class SealedReplayEvidence(ContractModel):
    evidence_id: Identifier
    strategy_version_id: Identifier
    family: Identifier
    horizon_sessions: int
    data_snapshot_id: Identifier
    window_start: date
    window_end: date
    universe_version: Identifier
    execution_assumption_version: Identifier
    metrics: EvidenceMetrics
    yearly: tuple[YearEvidence, ...]
    failures: tuple[FailureEvidence, ...]
    limitations: tuple[Identifier, ...]
    result_hash: ContentHash


class EvidenceBundle(ContractModel):
    bundle_id: Identifier
    purpose: Literal["sealed_replay"]
    data_snapshot_id: Identifier
    frozen_candidate_set_id: Identifier
    development_cutoff: date
    sealed_start: date
    sealed_end: date
    evidence: tuple[SealedReplayEvidence, ...]
    created_at: AwareDatetime
    broker_enabled: Literal[False] = False


class PromotionDecision(ContractModel):
    decision_id: Identifier
    strategy_version_id: Identifier
    evidence_bundle_id: Identifier
    evidence_id: Identifier
    sleeve: Literal["tactical"]
    outcome: Literal["promoted", "rejected"]
    rationale: str
    decided_at: AwareDatetime
    broker_enabled: Literal[False] = False


__all__ = [
    "EvidenceBundle",
    "EvidenceMetrics",
    "FailureEvidence",
    "PromotionDecision",
    "SealedReplayEvidence",
    "YearEvidence",
]
