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
)
from .legacy_constraints import LegacyConstraintAnnualCompactor
from .legacy_corporate_actions import DuckDBCorporateActionProjector
from .legacy_silver import LegacyAnnualCompactor, discover_legacy_release
from .legacy_status import DuckDBHistoricalStatusProjector
from .miniqmt_probe import MiniQMTCapabilityProbe
from .parquet import DuckDBParquetEncoder
from .provider_config import TushareProbeConfig, load_tushare_probe_config
from .tushare_client import TushareHttpClient, TushareRequestError
from .tushare_probe import TushareCapabilityProbe

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
    "MiniQMTCapabilityProbe",
    "TushareCapabilityProbe",
    "TushareHttpClient",
    "TushareProbeConfig",
    "TushareRequestError",
    "discover_legacy_release",
    "load_tushare_probe_config",
]
