"""Strategy Research adapters."""

from .promotion_ledger import SQLitePromotionDecisionStore
from .sealed_snapshot import DuckDBSealedReplaySource
from .snapshot_market import SnapshotMarketReader

__all__ = [
    "DuckDBSealedReplaySource",
    "SQLitePromotionDecisionStore",
    "SnapshotMarketReader",
]
