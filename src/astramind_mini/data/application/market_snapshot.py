"""Publish the first bounded, production Tushare DataSnapshot."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime

from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot

from ..contracts import (
    AdjustmentFactorObservation,
    DailyBarObservation,
    DatasetManifest,
    RawRecordEnvelope,
    SecurityMasterObservation,
    TradeCalendarObservation,
)
from ..ports import (
    DataArtifactLedger,
    DatasetStore,
    HistoricalMarketDataProvider,
    ParquetEncoder,
    ProviderTable,
    RawRecordStore,
    SnapshotStore,
)
from .dataset_schemas import (
    ADJUSTMENT_FACTOR_COLUMNS,
    DAILY_BAR_COLUMNS,
    SECURITY_MASTER_COLUMNS,
    TRADE_CALENDAR_COLUMNS,
)
from .datasets import DataSnapshotBuilder, build_dataset_manifest
from .identity import canonical_json, content_hash
from .normalization import (
    normalize_adjustment_factors,
    normalize_daily_bars,
    normalize_security_master,
    normalize_trade_calendar,
)
from .publication_policy import (
    ADJUSTMENT_FIELDS,
    CALENDAR_FIELDS,
    DAILY_FIELDS,
    PRIMARY_KEYS,
    PROVIDER_LIMIT,
    SECURITY_FIELDS,
    UNITS,
    active_security_count,
    completed_session_cutoff,
    date_chunks,
    latest_common_open_date,
)
from .publication_validation import validate_market_coverage


@dataclass(frozen=True, slots=True)
class SnapshotPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    latest_trade_date: date
    row_counts: dict[str, int]


class ProductionSnapshotService:
    def __init__(
        self,
        *,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        dataset_store: DatasetStore,
        snapshot_store: SnapshotStore,
        ledger: DataArtifactLedger,
        encoder: ParquetEncoder,
    ) -> None:
        self._provider = provider
        self._raw_store = raw_store
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger
        self._encoder = encoder

    async def publish(self, requested_at: datetime | None = None) -> SnapshotPublication:
        started_at = requested_at or datetime.now(UTC)
        cutoff = completed_session_cutoff(started_at)
        security_tables = await self._security_master()
        calendar_tables = await self._trade_calendars(cutoff)
        securities = normalize_security_master(security_tables)
        calendars = normalize_trade_calendar(calendar_tables)
        trade_date = latest_common_open_date(calendars, cutoff)
        daily_table = await self._query(
            "daily",
            {"trade_date": trade_date.strftime("%Y%m%d")},
            DAILY_FIELDS,
        )
        factor_table = await self._query(
            "adj_factor",
            {"trade_date": trade_date.strftime("%Y%m%d")},
            ADJUSTMENT_FIELDS,
        )
        daily = normalize_daily_bars(daily_table)
        factors = normalize_adjustment_factors(factor_table)
        if not securities or not calendars or not daily or not factors:
            raise ValueError("生产快照数据集不能为空")
        factor_only_count = validate_market_coverage(
            securities,
            daily,
            factors,
            trade_date,
        )
        manifests = self._publish_manifests(
            securities,
            calendars,
            daily,
            factors,
            security_tables,
            calendar_tables,
            daily_table,
            factor_table,
            trade_date,
            factor_only_count,
        )
        published_at = max(
            table.received_at
            for table in [*security_tables, *calendar_tables, daily_table, factor_table]
        )
        snapshot = DataSnapshotBuilder().build(
            manifests=manifests,
            as_of=published_at,
            created_at=published_at,
            code_identity="wp-0002b-v1",
            known_gaps=("historical_daily_backfill_pending",),
        )
        snapshot_path = self._snapshot_store.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        return SnapshotPublication(
            snapshot=snapshot,
            manifests=manifests,
            latest_trade_date=trade_date,
            row_counts={item.dataset_name: item.row_count for item in manifests},
        )

    async def _security_master(self) -> tuple[ProviderTable, ...]:
        tables = []
        for status in ("L", "D", "P"):
            tables.append(
                await self._query(
                    "stock_basic",
                    {"list_status": status},
                    SECURITY_FIELDS,
                )
            )
        return tuple(tables)

    async def _trade_calendars(self, cutoff: date) -> tuple[ProviderTable, ...]:
        tables = []
        for exchange in ("SSE", "SZSE"):
            for start, end in date_chunks(date(1990, 1, 1), cutoff):
                tables.append(
                    await self._query(
                        "trade_cal",
                        {
                            "exchange": exchange,
                            "start_date": start.strftime("%Y%m%d"),
                            "end_date": end.strftime("%Y%m%d"),
                        },
                        CALENDAR_FIELDS,
                    )
                )
        return tuple(tables)

    async def _query(
        self,
        api_name: str,
        params: dict[str, object],
        fields: Sequence[str],
    ) -> ProviderTable:
        table = await self._provider.query(api_name, params=params, fields=fields)
        if len(table.rows) >= PROVIDER_LIMIT:
            raise ValueError(f"{api_name} 达到提供方行数上限，拒绝发布可能截断的数据")
        envelope = RawRecordEnvelope(
            provider="tushare",
            interface_name=api_name,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw_store.append(envelope, table.raw_body)
        return table

    def _publish_manifests(
        self,
        securities: Sequence[SecurityMasterObservation],
        calendars: Sequence[TradeCalendarObservation],
        daily: Sequence[DailyBarObservation],
        factors: Sequence[AdjustmentFactorObservation],
        security_tables: Sequence[ProviderTable],
        calendar_tables: Sequence[ProviderTable],
        daily_table: ProviderTable,
        factor_table: ProviderTable,
        trade_date: date,
        factor_only_count: int,
    ) -> tuple[DatasetManifest, ...]:
        active = active_security_count(securities, trade_date)
        specs = (
            _DatasetSpec(
                "security_master",
                securities,
                SECURITY_MASTER_COLUMNS,
                security_tables,
                (date(1990, 12, 19), trade_date),
                ("current_name_history_not_available",),
                {"rows": len(securities), "active_as_of": active},
                tuple(row.instrument_id for row in securities),
            ),
            _DatasetSpec(
                "trade_calendar",
                calendars,
                TRADE_CALENDAR_COLUMNS,
                calendar_tables,
                (date(1990, 1, 1), trade_date),
                ("bse_uses_common_a_share_calendar",),
                {"rows": len(calendars), "exchanges": 2},
                ("SSE", "SZSE"),
            ),
            _DatasetSpec(
                "daily_market",
                daily,
                DAILY_BAR_COLUMNS,
                (daily_table,),
                (trade_date, trade_date),
                ("single_completed_session_only", "suspension_state_pending"),
                {"rows": len(daily), "active_security_count": active},
                tuple(row.instrument_id for row in daily),
            ),
            _DatasetSpec(
                "adjustment_factor",
                factors,
                ADJUSTMENT_FACTOR_COLUMNS,
                (factor_table,),
                (trade_date, trade_date),
                (
                    "historical_adjustment_factors_pending",
                    *(("factor_rows_without_daily_bar",) if factor_only_count else ()),
                ),
                {
                    "rows": len(factors),
                    "daily_rows": len(daily),
                    "factor_without_daily_bar": factor_only_count,
                },
                tuple(row.instrument_id for row in factors),
            ),
        )
        return tuple(self._publish_spec(spec) for spec in specs)

    def _publish_spec(self, spec: _DatasetSpec) -> DatasetManifest:
        artifacts = {
            "data.parquet": self._encoder.encode(spec.rows, spec.columns),
            "coverage.json": canonical_json(spec.coverage),
        }
        manifest = build_dataset_manifest(
            dataset_name=spec.name,
            schema_version="1.0.0",
            provider="tushare",
            source_endpoint=spec.tables[0].source_endpoint,
            request_identity=content_hash(sorted(table.request_identity for table in spec.tables)),
            retrieved_at=max(table.received_at for table in spec.tables),
            market_timezone="Asia/Shanghai",
            date_range=spec.date_range,
            universe=spec.universe,
            primary_key=PRIMARY_KEYS[spec.name],
            availability_rule="provider retrieved_at; conservative first-ingestion availability",
            units=UNITS[spec.name],
            row_count=len(spec.rows),
            artifacts=artifacts,
            known_gaps=spec.known_gaps,
        )
        path = self._dataset_store.publish(manifest, artifacts)
        self._ledger.record_dataset(manifest, path)
        return manifest


@dataclass(frozen=True, slots=True)
class _DatasetSpec:
    name: str
    rows: Sequence[BaseModel]
    columns: Sequence[tuple[str, str]]
    tables: Sequence[ProviderTable]
    date_range: tuple[date, date]
    known_gaps: tuple[str, ...]
    coverage: dict[str, int]
    universe: tuple[str, ...]


__all__ = ["ProductionSnapshotService", "SnapshotPublication"]
