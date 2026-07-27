"""Stable public thin-waist contracts."""

from .data import DatasetRef, DataSnapshot, FeatureSnapshot
from .execution import ExecutionEvent, ExecutionMode, OrderPlan, StandingMandate
from .portfolio import OptimizationProblem, OptimizationResult, PortfolioTarget, Sleeve
from .research import PredictionBatch, StrategyVersion

PUBLIC_CONTRACTS = (
    DataSnapshot,
    FeatureSnapshot,
    StrategyVersion,
    PredictionBatch,
    OptimizationProblem,
    OptimizationResult,
    PortfolioTarget,
    StandingMandate,
    OrderPlan,
    ExecutionEvent,
)

__all__ = [
    "PUBLIC_CONTRACTS",
    "DataSnapshot",
    "DatasetRef",
    "ExecutionEvent",
    "ExecutionMode",
    "FeatureSnapshot",
    "OptimizationProblem",
    "OptimizationResult",
    "OrderPlan",
    "PortfolioTarget",
    "PredictionBatch",
    "Sleeve",
    "StandingMandate",
    "StrategyVersion",
]
