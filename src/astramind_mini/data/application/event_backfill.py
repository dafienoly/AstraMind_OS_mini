"""Resumable production backfill for REQ-2026-0005 tactical events."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
from pydantic import BaseModel

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest, RawRecordEnvelope
from ..ports import (
    DataArtifactLedger,
    EventDatasetCompactor,
    FileDatasetStore,
    HistoricalMarketDataProvider,
    ParquetEncoder,
    ProviderTable,
    RawRecordStore,
    ReleasableSnapshotStore,
)
from .dataset_schemas import (
    LHB_EVENT_COLUMNS,
    LHB_SEAT_COLUMNS,
    SHAREHOLDER_COUNT_COLUMNS,
)
from .datasets import DataSnapshotBuilder
from .event_backfill_support import (
    HOLDER_FIELDS,
    LHB_FIELDS,
    SEAT_FIELDS,
    EventBackfillPublication,
    artifact_paths,
    latest_received_at,
    request_count,
    request_is_intact,
    request_paths,
    seven_day_windows,
)
from .event_normalization import (
    normalize_lhb_events,
    normalize_lhb_seats,
    normalize_shareholder_counts,
)
from .event_publication import build_event_manifests
from .identity import content_hash, file_hash
from .state_files import load_state, save_state, write_bytes_atomic


class TacticalEventBackfillService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
        compactor: EventDatasetCompactor,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._raw_store = raw_store
        self._encoder = encoder
        self._compactor = compactor
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger

    async def run(
        self,
        *,
        base_snapshot_id: str,
        start_date: date,
        end_date: date,
        republish: bool = False,
    ) -> EventBackfillPublication:
        if start_date > end_date:
            raise ValueError("事件回填开始日期不能晚于结束日期")
        base = self._manifests(self._snapshot_store.get(base_snapshot_id))
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "start_date": start_date,
                "end_date": end_date,
                "policy": "req-0005-events-v1",
            }
        )
        staging = self._root / "imports" / import_id.rsplit(":", 1)[-1]
        state_path = staging / "state.json"
        state = load_state(state_path) or {
            "import_id": import_id,
            "started_at": datetime.now(UTC).isoformat(),
            "requests": {},
        }
        if (snapshot_id := state.get("snapshot_id")) and not republish:
            return self._completed(str(snapshot_id), state)
        trade_dates = self._trade_dates(base["trade_calendar"], start_date, end_date)
        await self._collect_daily(trade_dates, staging, state, state_path)
        await self._collect_holders(start_date, end_date, staging, state, state_path)
        annual = self._compact(start_date, end_date, staging, state)
        return self._publish(
            base, import_id, start_date, end_date, staging, state, state_path, annual
        )

    async def _collect_daily(
        self,
        trade_dates: tuple[date, ...],
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> None:
        for trade_date in trade_dates:
            key = trade_date.strftime("%Y%m%d")
            await self._cached_query(
                api_name="top_list",
                key=key,
                params={"trade_date": key},
                fields=LHB_FIELDS,
                columns=LHB_EVENT_COLUMNS,
                normalizer=normalize_lhb_events,
                provider_limit=10_000,
                staging=staging,
                state=state,
                state_path=state_path,
            )
            await self._cached_query(
                api_name="top_inst",
                key=key,
                params={"trade_date": key},
                fields=SEAT_FIELDS,
                columns=LHB_SEAT_COLUMNS,
                normalizer=normalize_lhb_seats,
                provider_limit=10_000,
                staging=staging,
                state=state,
                state_path=state_path,
            )

    async def _collect_holders(
        self,
        start_date: date,
        end_date: date,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> None:
        for window_start, window_end in seven_day_windows(start_date, end_date):
            await self._collect_holder_window(window_start, window_end, staging, state, state_path)

    async def _collect_holder_window(
        self,
        window_start: date,
        window_end: date,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> None:
        key = f"{window_start:%Y%m%d}-{window_end:%Y%m%d}"
        try:
            await self._cached_query(
                api_name="stk_holdernumber",
                key=key,
                params={
                    "start_date": window_start.strftime("%Y%m%d"),
                    "end_date": window_end.strftime("%Y%m%d"),
                },
                fields=HOLDER_FIELDS,
                columns=SHAREHOLDER_COUNT_COLUMNS,
                normalizer=normalize_shareholder_counts,
                provider_limit=3_000,
                staging=staging,
                state=state,
                state_path=state_path,
            )
        except ProviderRowLimitError:
            if window_start == window_end:
                raise
            midpoint = date.fromordinal((window_start.toordinal() + window_end.toordinal()) // 2)
            await self._collect_holder_window(window_start, midpoint, staging, state, state_path)
            await self._collect_holder_window(
                date.fromordinal(midpoint.toordinal() + 1),
                window_end,
                staging,
                state,
                state_path,
            )

    async def _cached_query(
        self,
        *,
        api_name: str,
        key: str,
        params: Mapping[str, object],
        fields: Sequence[str],
        columns: Sequence[tuple[str, str]],
        normalizer: Callable[[ProviderTable], Sequence[BaseModel]],
        provider_limit: int,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
    ) -> None:
        requests = state["requests"]
        assert isinstance(requests, dict)
        identity = f"{api_name}:{key}"
        current = requests.get(identity)
        if isinstance(current, dict) and request_is_intact(current):
            return
        table = await self._provider.query(api_name, params=params, fields=fields)
        if len(table.rows) >= provider_limit:
            raise ProviderRowLimitError(f"{api_name}:{key} 达到提供方上限，拒绝发布可能截断的数据")
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
        rows = normalizer(table)
        path = staging / "requests" / api_name / f"{key}.parquet"
        write_bytes_atomic(path, self._encoder.encode(rows, columns))
        requests[identity] = {
            "api_name": api_name,
            "key": key,
            "path": str(path),
            "hash": file_hash(path),
            "rows": len(rows),
            "received_at": table.received_at.isoformat(),
            "request_identity": table.request_identity,
        }
        save_state(state_path, state)

    def _compact(
        self,
        start_date: date,
        end_date: date,
        staging: Path,
        state: dict[str, object],
    ) -> dict[str, dict[int, dict[str, object]]]:
        requests = state["requests"]
        assert isinstance(requests, dict)
        definitions = {
            "lhb_event": (
                "top_list",
                ("trade_date", "instrument_id", "source_record_hash"),
                "trade_date",
            ),
            "lhb_seat": (
                "top_inst",
                ("trade_date", "instrument_id", "source_record_hash"),
                "trade_date",
            ),
            "shareholder_count": (
                "stk_holdernumber",
                ("announced_on", "instrument_id", "reporting_period", "source_record_hash"),
                "announced_on",
            ),
        }
        annual: dict[str, dict[int, dict[str, object]]] = {}
        for dataset, (api_name, ordering, date_column) in definitions.items():
            annual[dataset] = {}
            for year in range(start_date.year, end_date.year + 1):
                sources = request_paths(requests, api_name, year)
                output = staging / "annual" / f"{dataset}-{year}.parquet"
                stats = self._compactor.compact(
                    source_files=sources,
                    output=output,
                    order_by=ordering,
                    date_column=date_column,
                )
                annual[dataset][year] = {
                    "path": str(output),
                    "hash": file_hash(output),
                    **stats,
                }
        return annual

    def _publish(
        self,
        base: dict[str, DatasetManifest],
        import_id: str,
        start_date: date,
        end_date: date,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        annual: dict[str, dict[int, dict[str, object]]],
    ) -> EventBackfillPublication:
        retrieved_at = latest_received_at(state)
        manifests, artifacts = build_event_manifests(
            import_id=import_id,
            start_date=start_date,
            end_date=end_date,
            annual=annual,
            staging=staging,
            retrieved_at=retrieved_at,
        )
        for manifest in manifests:
            path = self._dataset_store.publish_files(manifest, artifacts[manifest.dataset_name])
            self._ledger.record_dataset(manifest, path)
        snapshot = DataSnapshotBuilder().build(
            manifests=(*base.values(), *manifests),
            as_of=retrieved_at,
            created_at=retrieved_at,
            code_identity="req-0005-events-v1",
        )
        snapshot_path = self._snapshot_store.publish(snapshot)
        self._ledger.record_snapshot(snapshot, snapshot_path)
        self._snapshot_store.activate(snapshot, snapshot_path)
        for manifest in manifests:
            digest = manifest.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / manifest.dataset_name / digest / "manifest.json"
            self._dataset_store.activate(manifest, path)
        state["snapshot_id"] = snapshot.snapshot_id
        state["completed_at"] = datetime.now(UTC).isoformat()
        save_state(state_path, state)
        return EventBackfillPublication(snapshot, manifests, request_count(state))

    def _completed(
        self,
        snapshot_id: str,
        state: dict[str, object],
    ) -> EventBackfillPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._manifests(snapshot)
        selected = tuple(manifests[name] for name in ("lhb_event", "lhb_seat", "shareholder_count"))
        return EventBackfillPublication(snapshot, selected, request_count(state))

    def _manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        result = {}
        for ref in snapshot.datasets:
            digest = ref.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / ref.dataset_name / digest / "manifest.json"
            result[ref.dataset_name] = DatasetManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return result

    def _trade_dates(
        self,
        manifest: DatasetManifest,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        paths = artifact_paths(self._root, manifest)
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT calendar_date FROM read_parquet(?)
                WHERE exchange = 'SSE' AND is_open
                  AND calendar_date BETWEEN ? AND ?
                ORDER BY calendar_date
                """,
                [[str(path) for path in paths], start_date, end_date],
            ).fetchall()
        if not rows:
            raise ValueError("事件回填区间没有交易日")
        return tuple(row[0] for row in rows)


class ProviderRowLimitError(ValueError):
    """A request must be split or failed because the provider may have truncated it."""


__all__ = ["EventBackfillPublication", "TacticalEventBackfillService"]
