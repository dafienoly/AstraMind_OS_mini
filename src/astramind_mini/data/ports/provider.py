"""Provider and persistence ports owned by the Data context."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest, ProbeReport, RawRecordEnvelope


class MarketDataCapabilityProbe(Protocol):
    async def probe(self) -> tuple[ProbeReport, tuple[tuple[RawRecordEnvelope, object], ...]]: ...


@dataclass(frozen=True, slots=True)
class ProviderTable:
    api_name: str
    fields: tuple[str, ...]
    rows: tuple[dict[str, object], ...]
    raw_body: object
    request_identity: str
    received_at: datetime
    source_endpoint: str


class HistoricalMarketDataProvider(Protocol):
    async def query(
        self,
        api_name: str,
        *,
        params: Mapping[str, object],
        fields: Sequence[str],
    ) -> ProviderTable: ...


class ParquetEncoder(Protocol):
    def encode(
        self,
        rows: Sequence[BaseModel],
        columns: Sequence[tuple[str, str]],
    ) -> bytes: ...


class LegacyMarketRelease(Protocol):
    @property
    def dataset_version(self) -> str: ...

    @property
    def release_content_hash(self) -> str: ...

    @property
    def created_at(self) -> datetime: ...

    def dates(self, table: str) -> frozenset[str]: ...

    def files(self, table: str) -> tuple[Path, ...]: ...

    def files_for_year(self, table: str, year: int) -> tuple[Path, ...]: ...


class AnnualMarketCompactor(Protocol):
    def compact(
        self,
        *,
        table: str,
        source_files: tuple[Path, ...],
        supplement_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> tuple[int, int]: ...

    def validate_pair(self, daily: Path, factors: Path) -> tuple[int, int]: ...


class AnnualConstraintCompactor(Protocol):
    def compact(
        self,
        *,
        table: str,
        source_files: tuple[Path, ...],
        supplement_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> tuple[int, int]: ...

    def validate(self, table: str, path: Path) -> dict[str, int]: ...


class HistoricalStatusProjector(Protocol):
    def compact_name_history(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]: ...

    def project_year(
        self,
        *,
        year: int,
        security_master: Path,
        trade_calendar: Path,
        daily_files: tuple[Path, ...],
        price_limit_files: tuple[Path, ...],
        suspension_files: tuple[Path, ...],
        name_history: Path,
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]: ...


class CorporateActionProjector(Protocol):
    def compact_actions(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        imported_at: datetime,
    ) -> dict[str, int]: ...

    def build_factor_anchors(
        self,
        *,
        factor_files: tuple[Path, ...],
        output: Path,
    ) -> dict[str, int]: ...

    def project_year(
        self,
        *,
        daily_files: tuple[Path, ...],
        factor_files: tuple[Path, ...],
        action_history: Path,
        factor_anchors: Path,
        previous_index_anchors: Path | None,
        output: Path,
        next_index_anchors: Path,
        imported_at: datetime,
    ) -> dict[str, int]: ...


class EventDatasetCompactor(Protocol):
    def compact(
        self,
        *,
        source_files: tuple[Path, ...],
        output: Path,
        order_by: tuple[str, ...],
        date_column: str,
        identity_columns: tuple[str, ...] = ("source_record_hash",),
    ) -> dict[str, object]: ...


class DataArtifactLedger(Protocol):
    def record_dataset(self, manifest: DatasetManifest, manifest_path: Path) -> None: ...

    def record_snapshot(self, snapshot: DataSnapshot, manifest_path: Path) -> None: ...


class RawRecordStore(Protocol):
    def append(self, envelope: RawRecordEnvelope, payload: object) -> Path: ...


class DatasetStore(Protocol):
    def publish(
        self,
        manifest: DatasetManifest,
        artifacts: Mapping[str, bytes],
    ) -> Path: ...


class FileDatasetStore(DatasetStore, Protocol):
    def publish_files(
        self,
        manifest: DatasetManifest,
        artifacts: Mapping[str, tuple[Path, str]],
    ) -> Path: ...

    def activate(self, manifest: DatasetManifest, manifest_path: Path) -> None: ...


class SnapshotStore(Protocol):
    def publish(self, snapshot: DataSnapshot) -> Path: ...

    def get(self, snapshot_id: str) -> DataSnapshot: ...


class ReleasableSnapshotStore(SnapshotStore, Protocol):
    def activate(self, snapshot: DataSnapshot, manifest_path: Path) -> None: ...


class SnapshotQuery(Protocol):
    def query_parquet(
        self,
        manifest: DatasetManifest,
        artifact_name: str,
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[tuple[Any, ...]]: ...

    def query_parquet_set(
        self,
        manifest: DatasetManifest,
        artifact_names: Sequence[str],
        sql: str,
        parameters: Sequence[Any] = (),
    ) -> list[tuple[Any, ...]]: ...


__all__ = [
    "AnnualConstraintCompactor",
    "AnnualMarketCompactor",
    "CorporateActionProjector",
    "DataArtifactLedger",
    "DatasetStore",
    "EventDatasetCompactor",
    "FileDatasetStore",
    "HistoricalMarketDataProvider",
    "HistoricalStatusProjector",
    "LegacyMarketRelease",
    "MarketDataCapabilityProbe",
    "ParquetEncoder",
    "ProviderTable",
    "RawRecordStore",
    "ReleasableSnapshotStore",
    "SnapshotQuery",
    "SnapshotStore",
]
