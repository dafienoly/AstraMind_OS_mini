"""Strategy Research adapters."""

from .market_model_readiness import (
    MarketModelReadinessItem,
    MarketModelReadinessReader,
    MarketModelReadinessReport,
)
from .promotion_ledger import SQLitePromotionDecisionStore
from .sealed_snapshot import DuckDBSealedReplaySource
from .snapshot_market import SnapshotMarketReader

__all__ = [
    "DuckDBSealedReplaySource",
    "MarketModelReadinessItem",
    "MarketModelReadinessReader",
    "MarketModelReadinessReport",
    "SQLitePromotionDecisionStore",
    "SnapshotMarketReader",
]
