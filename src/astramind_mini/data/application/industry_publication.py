"""Immutable manifest and snapshot publication for the industry foundation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from ..ports import DataArtifactLedger, FileDatasetStore, ReleasableSnapshotStore
from .datasets import DataSnapshotBuilder, build_dataset_manifest_from_hashes
from .identity import file_hash
from .state_files import save_state

DatasetDefinition = tuple[
    str,
    Path,
    int,
    tuple[str, ...],
    tuple[date, date],
    str,
    tuple[str, ...],
    tuple[str, ...],
]


@dataclass(frozen=True, slots=True)
class IndustryFoundationPublication:
    snapshot: DataSnapshot
    manifests: tuple[DatasetManifest, ...]
    request_count: int


def publish_industry_foundation(
    *,
    data_root: Path,
    base: dict[str, DatasetManifest],
    import_id: str,
    end_date: date,
    taxonomy_path: Path,
    membership_path: Path,
    daily_path: Path,
    taxonomy_rows: int,
    membership_stats: dict[str, object],
    daily_stats: dict[str, object],
    state: dict[str, object],
    state_path: Path,
    dataset_store: FileDatasetStore,
    snapshot_store: ReleasableSnapshotStore,
    ledger: DataArtifactLedger,
) -> IndustryFoundationPublication:
    requests = _requests(state)
    retrieved_at = max(
        datetime.fromisoformat(str(value["received_at"]))
        for value in requests.values()
        if isinstance(value, dict)
    )
    manifests, artifacts = _manifests_and_artifacts(
        import_id=import_id,
        end_date=end_date,
        retrieved_at=retrieved_at,
        taxonomy_path=taxonomy_path,
        membership_path=membership_path,
        daily_path=daily_path,
        taxonomy_rows=taxonomy_rows,
        membership_stats=membership_stats,
        daily_stats=daily_stats,
    )
    for manifest in manifests:
        manifest_path = dataset_store.publish_files(manifest, artifacts[manifest.dataset_name])
        ledger.record_dataset(manifest, manifest_path)
    snapshot = DataSnapshotBuilder().build(
        manifests=(*base.values(), *manifests),
        as_of=retrieved_at,
        created_at=retrieved_at,
        code_identity="req-0008-industry-foundation-v1",
    )
    snapshot_path = snapshot_store.publish(snapshot)
    ledger.record_snapshot(snapshot, snapshot_path)
    snapshot_store.activate(snapshot, snapshot_path)
    for manifest in manifests:
        digest = manifest.dataset_version.rsplit(":", 1)[-1]
        dataset_store.activate(
            manifest,
            data_root / "datasets" / manifest.dataset_name / digest / "manifest.json",
        )
    state["snapshot_id"] = snapshot.snapshot_id
    state["completed_at"] = datetime.now(UTC).isoformat()
    save_state(state_path, state)
    return IndustryFoundationPublication(snapshot, manifests, len(requests))


def _manifests_and_artifacts(
    *,
    import_id: str,
    end_date: date,
    retrieved_at: datetime,
    taxonomy_path: Path,
    membership_path: Path,
    daily_path: Path,
    taxonomy_rows: int,
    membership_stats: dict[str, object],
    daily_stats: dict[str, object],
) -> tuple[tuple[DatasetManifest, ...], dict[str, dict[str, tuple[Path, str]]]]:
    definitions = _dataset_definitions(
        end_date=end_date,
        retrieved_at=retrieved_at,
        taxonomy_path=taxonomy_path,
        membership_path=membership_path,
        daily_path=daily_path,
        taxonomy_rows=taxonomy_rows,
        membership_stats=membership_stats,
        daily_stats=daily_stats,
    )
    manifests, artifacts = [], {}
    endpoints = {
        "industry_taxonomy": "index_classify",
        "industry_membership": "index_member_all",
        "industry_index_daily": "sw_daily",
    }
    for name, path, rows, primary_key, dates, availability, units, gaps in definitions:
        artifact_hash = file_hash(path)
        manifest = build_dataset_manifest_from_hashes(
            dataset_name=name,
            schema_version="1.0.0",
            provider="tushare",
            source_endpoint=endpoints[name],
            request_identity=import_id,
            retrieved_at=retrieved_at,
            market_timezone="Asia/Shanghai",
            date_range=dates,
            universe=(),
            primary_key=primary_key,
            availability_rule=availability,
            units=units,
            row_count=rows,
            artifact_hashes={f"{name}.parquet": artifact_hash},
            known_gaps=gaps,
        )
        manifests.append(manifest)
        artifacts[name] = {f"{name}.parquet": (path, artifact_hash)}
    return tuple(manifests), artifacts


def _dataset_definitions(
    *,
    end_date: date,
    retrieved_at: datetime,
    taxonomy_path: Path,
    membership_path: Path,
    daily_path: Path,
    taxonomy_rows: int,
    membership_stats: dict[str, object],
    daily_stats: dict[str, object],
) -> tuple[DatasetDefinition, ...]:
    overlap_count = _integer(membership_stats["same_industry_overlap_rows"])
    overlap_gaps = (
        (f"provider_overlapping_same_industry_intervals:{overlap_count}",) if overlap_count else ()
    )
    return (
        (
            "industry_taxonomy",
            taxonomy_path,
            taxonomy_rows,
            ("industry_code",),
            (retrieved_at.date(), retrieved_at.date()),
            "retrieved_at",
            ("taxonomy:SW2021", "level:L1"),
            (),
        ),
        (
            "industry_membership",
            membership_path,
            _integer(membership_stats["rows"]),
            ("industry_code", "instrument_id", "effective_from", "effective_to"),
            (date.fromisoformat(str(membership_stats["start_date"])), end_date),
            "effective_from 18:00 Asia/Shanghai; effective_to is exclusive",
            ("taxonomy:SW2021", "level:L1"),
            (
                "historical_membership_publication_time_unavailable",
                "pre_2021_membership_is_provider_backcast_under_SW2021",
                *overlap_gaps,
            ),
        ),
        (
            "industry_index_daily",
            daily_path,
            _integer(daily_stats["rows"]),
            ("industry_code", "trade_date"),
            (
                date.fromisoformat(str(daily_stats["start_date"])),
                date.fromisoformat(str(daily_stats["end_date"])),
            ),
            "trade_date 18:00 Asia/Shanghai",
            (
                "price:index_points",
                "volume:provider_native_unverified",
                "amount:provider_native_unverified",
                "valuation:provider_native",
            ),
            (
                "provider_native_volume_amount_market_value_units_unverified",
                "provider_ohlc_rounding_tolerance_up_to_1bp",
            ),
        ),
    )


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("行业数据统计不是整数")
    return value


def _requests(state: dict[str, object]) -> dict[object, object]:
    requests = state["requests"]
    if not isinstance(requests, dict):
        raise ValueError("行业回填请求状态无效")
    return requests


__all__ = ["IndustryFoundationPublication", "publish_industry_foundation"]
