"""Daily tactical-event increments merged into exact immutable event datasets."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from ..contracts import DatasetManifest
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable, RawRecordStore
from .dataset_schemas import (
    LHB_EVENT_COLUMNS,
    LHB_SEAT_COLUMNS,
    SHAREHOLDER_COUNT_COLUMNS,
)
from .event_backfill_support import HOLDER_FIELDS, LHB_FIELDS, SEAT_FIELDS
from .event_merge import (
    EVENT_DATASETS,
    combined_date_range,
    load_current_event_manifests,
    merge_event_annual,
)
from .event_normalization import (
    normalize_lhb_events,
    normalize_lhb_seats,
    normalize_shareholder_counts,
)
from .event_publication import build_event_manifests
from .historical_publication import FileArtifacts
from .identity import content_hash, file_hash
from .raw_records import preserve_provider_table_raw
from .state_files import save_state, write_bytes_atomic


@dataclass(frozen=True, slots=True)
class DailyEventInputs:
    manifests: dict[str, DatasetManifest]
    artifacts: FileArtifacts
    retrieved_at: datetime


def event_base_manifests(
    root: Path,
    snapshot_manifests: dict[str, DatasetManifest],
) -> dict[str, DatasetManifest]:
    current = load_current_event_manifests(root)
    result = {}
    for name in EVENT_DATASETS:
        manifest = snapshot_manifests.get(name) or current.get(name)
        if manifest is not None:
            result[name] = manifest
    return result


async def prepare_daily_event_inputs(
    *,
    root: Path,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    snapshot_manifests: dict[str, DatasetManifest],
    workspace: Path,
    state: dict[str, object],
    state_path: Path,
    target_date: date,
) -> DailyEventInputs | None:
    base = event_base_manifests(root, snapshot_manifests)
    if not base:
        return None
    if set(base) != set(EVENT_DATASETS):
        raise ValueError("日度事件增量缺少完整基础数据集")
    event_state = state.setdefault("events", {})
    if not isinstance(event_state, dict):
        raise ValueError("日度事件请求状态格式无效")
    requests = []
    definitions = (
        ("lhb_event", "top_list", LHB_FIELDS, LHB_EVENT_COLUMNS, normalize_lhb_events, 10_000),
        ("lhb_seat", "top_inst", SEAT_FIELDS, LHB_SEAT_COLUMNS, normalize_lhb_seats, 10_000),
        (
            "shareholder_count",
            "stk_holdernumber",
            HOLDER_FIELDS,
            SHAREHOLDER_COUNT_COLUMNS,
            normalize_shareholder_counts,
            3_000,
        ),
    )
    for dataset, api_name, fields, columns, normalizer, limit in definitions:
        item = await _collect(
            dataset=dataset,
            api_name=api_name,
            fields=fields,
            columns=columns,
            normalizer=normalizer,
            provider_limit=limit,
            provider=provider,
            raw_store=raw_store,
            encoder=encoder,
            workspace=workspace,
            event_state=event_state,
            state=state,
            state_path=state_path,
            target_date=target_date,
        )
        requests.append(item)
    incremental: dict[str, dict[int, dict[str, object]]] = {
        str(item["dataset"]): {
            target_date.year: {
                "path": str(item["path"]),
                "hash": str(item["hash"]),
            }
        }
        for item in requests
    }
    annual = merge_event_annual(
        root=root,
        base=base,
        incremental=incremental,
        staging=workspace / "events",
    )
    request_identity = content_hash(
        {
            "policy": "daily-events-v1",
            "target_date": target_date,
            "base_versions": {name: item.dataset_version for name, item in base.items()},
            "requests": [item["request_identity"] for item in requests],
        }
    )
    retrieved_at = max(datetime.fromisoformat(str(item["received_at"])) for item in requests)
    date_range = combined_date_range(base, target_date, target_date)
    manifests, artifacts = build_event_manifests(
        import_id=request_identity,
        start_date=date_range[0],
        end_date=date_range[1],
        annual=annual,
        staging=workspace / "events",
        retrieved_at=retrieved_at,
    )
    return DailyEventInputs(
        manifests={item.dataset_name: item for item in manifests},
        artifacts=artifacts,
        retrieved_at=retrieved_at,
    )


async def _collect(
    *,
    dataset: str,
    api_name: str,
    fields: tuple[str, ...],
    columns: tuple[tuple[str, str], ...],
    normalizer: Callable[[ProviderTable], Sequence[BaseModel]],
    provider_limit: int,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    workspace: Path,
    event_state: dict[str, object],
    state: dict[str, object],
    state_path: Path,
    target_date: date,
) -> dict[str, object]:
    cached = event_state.get(api_name)
    if isinstance(cached, dict):
        path = Path(str(cached.get("path", "")))
        if path.is_file() and file_hash(path) == cached.get("hash"):
            return {**cached, "dataset": dataset, "path": path}
    key = target_date.strftime("%Y%m%d")
    params = (
        {"start_date": key, "end_date": key}
        if api_name == "stk_holdernumber"
        else {"trade_date": key}
    )
    table = await provider.query(api_name, params=params, fields=fields)
    if len(table.rows) >= provider_limit:
        raise ValueError(f"{api_name}:{key} 达到提供方上限，拒绝可能截断的事件增量")
    _preserve_raw(table, raw_store)
    rows = normalizer(table)
    path = workspace / "events" / "requests" / f"{api_name}-{key}.parquet"
    write_bytes_atomic(path, encoder.encode(rows, columns))
    item: dict[str, object] = {
        "dataset": dataset,
        "path": str(path),
        "hash": file_hash(path),
        "rows": len(rows),
        "received_at": table.received_at.isoformat(),
        "request_identity": table.request_identity,
    }
    event_state[api_name] = item
    save_state(state_path, state)
    return {**item, "path": path}


def _preserve_raw(table: ProviderTable, raw_store: RawRecordStore) -> None:
    preserve_provider_table_raw(table, raw_store)


__all__ = [
    "DailyEventInputs",
    "event_base_manifests",
    "prepare_daily_event_inputs",
]
