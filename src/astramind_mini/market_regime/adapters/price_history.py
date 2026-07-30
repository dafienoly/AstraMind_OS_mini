"""Exact-snapshot, cursor-paged daily price history."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

from astramind_mini.contracts import DatasetRef, DataSnapshot

from ..contracts.price_history import HistoryWindow, InstrumentType, PriceHistoryPage
from .hierarchy_queries import snapshot_at, snapshot_paths
from .price_history_queries import HistoryQuery, price_candle, query_history

_DATASETS: dict[InstrumentType, str] = {
    "stock": "daily_market",
    "index": "broad_index_daily",
    "etf": "etf_daily",
}


class SnapshotPriceHistory:
    """Read complete history without losing snapshot or evidence-cutoff identity."""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(
        self,
        instrument_type: InstrumentType,
        instrument_id: str,
        *,
        window: HistoryWindow = "one_year",
        evidence_cutoff: date | None = None,
        start: date | None = None,
        end: date | None = None,
        cursor: date | None = None,
        page_size: int = 520,
    ) -> PriceHistoryPage:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        if not isinstance(pointer, dict) or not isinstance(pointer.get("snapshot_id"), str):
            raise ValueError("当前数据快照指针无效")
        return self.load(
            pointer["snapshot_id"],
            instrument_type,
            instrument_id,
            window=window,
            evidence_cutoff=evidence_cutoff,
            start=start,
            end=end,
            cursor=cursor,
            page_size=page_size,
        )

    def load(
        self,
        snapshot_id: str,
        instrument_type: InstrumentType,
        instrument_id: str,
        *,
        window: HistoryWindow = "one_year",
        evidence_cutoff: date | None = None,
        start: date | None = None,
        end: date | None = None,
        cursor: date | None = None,
        page_size: int = 520,
    ) -> PriceHistoryPage:
        if not 1 <= page_size <= 1000:
            raise ValueError("历史行情单页数量必须在 1 到 1000 之间")
        snapshot = snapshot_at(self._root, snapshot_id)
        cutoff = min(evidence_cutoff or snapshot.as_of.date(), snapshot.as_of.date())
        requested_end = min(end or cutoff, cutoff)
        paths = snapshot_paths(self._root, snapshot)
        dataset_name = _DATASETS[instrument_type]
        if dataset_name not in paths:
            raise ValueError(f"历史行情缺少数据集：{dataset_name}")
        identity_dataset = _identity_dataset(instrument_type)
        if identity_dataset is not None and identity_dataset not in paths:
            raise ValueError(f"历史行情缺少证券主表：{identity_dataset}")
        reference = next(item for item in snapshot.datasets if item.dataset_name == dataset_name)
        manifest = self._manifest(dataset_name, reference.dataset_version)
        query = query_history(
            paths,
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            dataset_name=dataset_name,
            window=window,
            cutoff=cutoff,
            requested_end=requested_end,
            start=start,
            cursor=cursor,
            page_size=page_size,
        )
        return _page(
            snapshot,
            reference,
            manifest,
            query,
            instrument_type=instrument_type,
            instrument_id=instrument_id,
            dataset_name=dataset_name,
            window=window,
            cutoff=cutoff,
            page_size=page_size,
        )

    def _manifest(self, dataset_name: str, dataset_version: str) -> dict[str, object]:
        digest = dataset_version.removeprefix("sha256:")
        raw = json.loads(
            (self._root / "datasets" / dataset_name / digest / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        if not isinstance(raw, dict):
            raise ValueError(f"历史行情数据集清单无效：{dataset_name}")
        value = cast(dict[str, object], raw)
        if value.get("dataset_version") != dataset_version:
            raise ValueError(f"历史行情数据集身份冲突：{dataset_name}")
        return value


def _page(
    snapshot: DataSnapshot,
    reference: DatasetRef,
    manifest: dict[str, object],
    query: HistoryQuery,
    *,
    instrument_type: InstrumentType,
    instrument_id: str,
    dataset_name: str,
    window: HistoryWindow,
    cutoff: date,
    page_size: int,
) -> PriceHistoryPage:
    has_more = len(query.rows) > page_size
    selected = query.rows[:page_size]
    raw_gaps = manifest.get("known_gaps", ())
    gaps = list(raw_gaps) if isinstance(raw_gaps, (list, tuple)) else []
    if query.coverage_start is None:
        gaps.append("instrument_history_unavailable")
    elif (
        query.identity.listing_date is not None
        and query.coverage_start > query.identity.listing_date
    ):
        gaps.append(f"history_starts_after_listing:{query.identity.listing_date.isoformat()}")
    return PriceHistoryPage(
        instrument_type=instrument_type,
        instrument_id=instrument_id,
        instrument_name=query.identity.name,
        data_snapshot_id=snapshot.snapshot_id,
        dataset_name=dataset_name,
        dataset_version=reference.dataset_version,
        dataset_content_hash=reference.content_hash,
        evidence_cutoff=cutoff,
        window=window,
        requested_start=query.requested_start,
        requested_end=query.requested_end,
        coverage_start=query.coverage_start,
        coverage_end=query.coverage_end,
        coverage_basis=(
            "official_launch_or_earliest_reliable_record"
            if instrument_type == "index"
            else "listing_date_or_earliest_reliable_record"
        ),
        listing_date=query.identity.listing_date,
        schema_version=reference.schema_version,
        bars=tuple(price_candle(instrument_type, row) for row in reversed(selected)),
        page_size=page_size,
        has_more=has_more,
        next_cursor=cast(date, selected[-1][0]) if has_more and selected else None,
        known_gaps=tuple(dict.fromkeys(str(item) for item in gaps)),
    )


def _identity_dataset(instrument_type: InstrumentType) -> str | None:
    if instrument_type == "stock":
        return "security_master"
    if instrument_type == "etf":
        return "etf_master"
    return None


__all__ = ["SnapshotPriceHistory"]
