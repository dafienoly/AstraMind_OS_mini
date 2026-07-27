"""Build file-backed manifests for imported historical market data."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..contracts import DatasetManifest
from ..ports import LegacyMarketRelease
from .datasets import build_dataset_manifest_from_hashes
from .identity import canonical_json, file_hash
from .state_files import write_bytes_atomic

FileArtifacts = dict[str, dict[str, tuple[Path, str]]]


def build_historical_manifests(
    *,
    base: dict[str, DatasetManifest],
    release: LegacyMarketRelease,
    import_id: str,
    expected_dates: frozenset[date],
    yearly: dict[int, dict[str, object]],
    staging: Path,
    finished_at: datetime,
) -> tuple[DatasetManifest, DatasetManifest, FileArtifacts]:
    coverage = {
        "source_dataset_version": release.dataset_version,
        "expected_sessions": len(expected_dates),
        "years": yearly,
    }
    artifacts: FileArtifacts = {
        "daily_market": {},
        "adjustment_factor": {},
    }
    for year, item in sorted(yearly.items()):
        daily_name = f"daily-market-{year}.parquet"
        factor_name = f"adjustment-factor-{year}.parquet"
        artifacts["daily_market"][daily_name] = (
            Path(str(item["daily_path"])),
            str(item["daily_hash"]),
        )
        artifacts["adjustment_factor"][factor_name] = (
            Path(str(item["factor_path"])),
            str(item["factor_hash"]),
        )
    for dataset_name in artifacts:
        path = staging / f"{dataset_name}-coverage.json"
        write_bytes_atomic(
            path,
            canonical_json({**coverage, "dataset_name": dataset_name}),
        )
        artifacts[dataset_name]["coverage.json"] = (path, file_hash(path))
    date_range = (min(expected_dates), max(expected_dates))
    universe = base["security_master"].universe
    daily_hashes = {name: value[1] for name, value in artifacts["daily_market"].items()}
    factor_hashes = {name: value[1] for name, value in artifacts["adjustment_factor"].items()}
    factor_only = sum(_integer(item["factor_only"]) for item in yearly.values())
    daily_manifest = build_dataset_manifest_from_hashes(
        dataset_name="daily_market",
        schema_version="1.1.0",
        provider="tushare",
        source_endpoint="legacy-astramind-silver+tushare",
        request_identity=import_id,
        retrieved_at=finished_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=universe,
        primary_key=("instrument_id", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=("price:CNY", "volume:lot", "amount:thousand_CNY"),
        row_count=sum(_integer(item["daily_rows"]) for item in yearly.values()),
        artifact_hashes=daily_hashes,
        known_gaps=("legacy_raw_payloads_external", "suspension_state_pending"),
    )
    factor_gaps = ["legacy_raw_payloads_external"]
    if factor_only:
        factor_gaps.append("factor_rows_without_daily_bar")
    factor_manifest = build_dataset_manifest_from_hashes(
        dataset_name="adjustment_factor",
        schema_version="1.1.0",
        provider="tushare",
        source_endpoint="legacy-astramind-silver+tushare",
        request_identity=import_id,
        retrieved_at=finished_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=universe,
        primary_key=("instrument_id", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=("adjustment_factor:ratio",),
        row_count=sum(_integer(item["factor_rows"]) for item in yearly.values()),
        artifact_hashes=factor_hashes,
        known_gaps=factor_gaps,
    )
    return daily_manifest, factor_manifest, artifacts


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("年度覆盖统计不是整数")
    return value


__all__ = ["FileArtifacts", "build_historical_manifests"]
