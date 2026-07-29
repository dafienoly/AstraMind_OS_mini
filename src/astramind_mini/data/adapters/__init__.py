"""Data adapters."""

from .control_ledger import DataControlLedger
from .daily_pipeline_store import DailyPipelineStore
from .duckdb_query import DuckDBSnapshotQuery
from .event_parquet import DuckDBEventDatasetCompactor
from .filesystem import (
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    ImmutableConflictError,
    SnapshotPointerAdvancedError,
)
from .legacy_constraints import LegacyConstraintAnnualCompactor
from .legacy_corporate_actions import DuckDBCorporateActionProjector
from .legacy_silver import LegacyAnnualCompactor, discover_legacy_release
from .legacy_status import DuckDBHistoricalStatusProjector
from .miniqmt_bridge import MiniQMTBridgeClient, MiniQMTBridgeError
from .miniqmt_probe import MiniQMTCapabilityProbe
from .miniqmt_realtime_feed import MiniQMTRealtimeFeed
from .miniqmt_source import MiniQMTSourceAdapter
from .parquet import DuckDBParquetEncoder
from .provider_config import TushareProbeConfig, load_tushare_probe_config
from .realtime_projection_store import RealtimeProjectionStore
from .realtime_watchlist_store import RealtimeWatchlistStore
from .routed_legacy_provider import RoutedHistoricalProvider
from .streaming_realtime_store import StreamingRealtimeStore
from .tushare_client import TushareHttpClient, TushareRequestError
from .tushare_probe import TushareCapabilityProbe
from .tushare_source import TushareSourceAdapter

__all__ = [
    "DailyPipelineStore",
    "DataControlLedger",
    "DuckDBCorporateActionProjector",
    "DuckDBEventDatasetCompactor",
    "DuckDBHistoricalStatusProjector",
    "DuckDBParquetEncoder",
    "DuckDBSnapshotQuery",
    "FilesystemDatasetStore",
    "FilesystemRawRecordStore",
    "FilesystemSnapshotStore",
    "ImmutableConflictError",
    "LegacyAnnualCompactor",
    "LegacyConstraintAnnualCompactor",
    "MiniQMTBridgeClient",
    "MiniQMTBridgeError",
    "MiniQMTCapabilityProbe",
    "MiniQMTRealtimeFeed",
    "MiniQMTSourceAdapter",
    "RealtimeProjectionStore",
    "RealtimeWatchlistStore",
    "RoutedHistoricalProvider",
    "SnapshotPointerAdvancedError",
    "StreamingRealtimeStore",
    "TushareCapabilityProbe",
    "TushareHttpClient",
    "TushareProbeConfig",
    "TushareRequestError",
    "TushareSourceAdapter",
    "discover_legacy_release",
    "load_tushare_probe_config",
]
