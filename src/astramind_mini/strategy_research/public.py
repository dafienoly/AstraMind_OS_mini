"""Imports allowed for consumers of the Strategy Research context."""

from .application import ManualPromotionService, SealedReplayRunner, build_evidence_bundle
from .contracts import (
    EvidenceBundle,
    PredictionBatch,
    PromotionDecision,
    SealedReplayEvidence,
    StrategyVersion,
)
from .domain.backtest_models import (
    BacktestAssumptions,
    BacktestResult,
    CandidateSignal,
    ResearchBar,
    UniverseDecision,
    UniverseRules,
)

__all__ = [
    "BacktestAssumptions",
    "BacktestResult",
    "CandidateSignal",
    "EvidenceBundle",
    "ManualPromotionService",
    "PredictionBatch",
    "PromotionDecision",
    "ResearchBar",
    "SealedReplayEvidence",
    "SealedReplayRunner",
    "StrategyVersion",
    "UniverseDecision",
    "UniverseRules",
    "build_evidence_bundle",
]
