"""Build file-backed manifests for WP-0002B-H2 datasets."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..contracts import DatasetManifest
from ..ports import LegacyMarketRelease
from .datasets import build_dataset_manifest_from_hashes
from .historical_publication import FileArtifacts
from .identity import canonical_json, file_hash
from .state_files import write_bytes_atomic

DATASETS = ("daily_basic", "price_limit", "suspension_event")


def build_constraint_manifests(
    *,
    base: dict[str, DatasetManifest],
    release: LegacyMarketRelease,
    import_id: str,
    expected_dates: frozenset[date],
    price_limit_dates: frozenset[date],
    yearly: dict[int, dict[str, object]],
    cross_coverage: dict[str, int],
    staging: Path,
    finished_at: datetime,
) -> tuple[tuple[DatasetManifest, ...], FileArtifacts]:
    artifacts = _build_artifacts(yearly)
    _add_coverage_files(
        artifacts=artifacts,
        release=release,
        expected_dates=expected_dates,
        price_limit_dates=price_limit_dates,
        yearly=yearly,
        cross_coverage=cross_coverage,
        staging=staging,
    )
    manifests = _build_manifests(
        universe=base["security_master"].universe,
        import_id=import_id,
        finished_at=finished_at,
        expected_dates=expected_dates,
        price_limit_dates=price_limit_dates,
        yearly=yearly,
        cross_coverage=cross_coverage,
        artifacts=artifacts,
    )
    return manifests, artifacts


def _build_artifacts(yearly: dict[int, dict[str, object]]) -> FileArtifacts:
    artifacts: FileArtifacts = {name: {} for name in DATASETS}
    for year, item in sorted(yearly.items()):
        for dataset_name in DATASETS:
            path_key = f"{dataset_name}_path"
            if path_key not in item:
                continue
            name = f"{dataset_name.replace('_', '-')}-{year}.parquet"
            artifacts[dataset_name][name] = (
                Path(str(item[path_key])),
                str(item[f"{dataset_name}_hash"]),
            )
    return artifacts


def _add_coverage_files(
    *,
    artifacts: FileArtifacts,
    release: LegacyMarketRelease,
    expected_dates: frozenset[date],
    price_limit_dates: frozenset[date],
    yearly: dict[int, dict[str, object]],
    cross_coverage: dict[str, int],
    staging: Path,
) -> None:
    source_tables = {
        "daily_basic": "daily_basic",
        "price_limit": "stk_limit",
        "suspension_event": "suspend_d",
    }
    for dataset_name in DATASETS:
        coverage_path = staging / f"{dataset_name}-coverage.json"
        coverage = {
            "dataset_name": dataset_name,
            "source_table": source_tables[dataset_name],
            "source_dataset_version": release.dataset_version,
            "expected_sessions": len(
                price_limit_dates if dataset_name == "price_limit" else expected_dates
            ),
            "years": yearly,
            "cross_dataset_coverage": cross_coverage,
        }
        write_bytes_atomic(coverage_path, canonical_json(coverage))
        artifacts[dataset_name]["coverage.json"] = (
            coverage_path,
            file_hash(coverage_path),
        )


def _build_manifests(
    *,
    universe: tuple[str, ...],
    import_id: str,
    finished_at: datetime,
    expected_dates: frozenset[date],
    price_limit_dates: frozenset[date],
    yearly: dict[int, dict[str, object]],
    cross_coverage: dict[str, int],
    artifacts: FileArtifacts,
) -> tuple[DatasetManifest, ...]:
    return (
        _manifest(
            "daily_basic",
            import_id,
            finished_at,
            (min(expected_dates), max(expected_dates)),
            universe,
            ("instrument_id", "trade_date"),
            "trade_date 18:00 Asia/Shanghai",
            (
                "turnover_rate:percent",
                "shares:ten_thousand_shares",
                "market_value:ten_thousand_CNY",
            ),
            yearly,
            artifacts,
            _daily_basic_gaps(cross_coverage),
        ),
        _manifest(
            "price_limit",
            import_id,
            finished_at,
            (min(price_limit_dates), max(price_limit_dates)),
            universe,
            ("instrument_id", "trade_date"),
            "trade_date 08:40 Asia/Shanghai",
            ("price:CNY",),
            yearly,
            artifacts,
            _price_limit_gaps(yearly, cross_coverage),
        ),
        _manifest(
            "suspension_event",
            import_id,
            finished_at,
            (min(expected_dates), max(expected_dates)),
            universe,
            (
                "instrument_id",
                "trade_date",
                "suspension_type",
                "suspension_timing",
            ),
            "trade_date 18:00 Asia/Shanghai; conservative when event time is absent",
            (),
            yearly,
            artifacts,
            (
                "legacy_raw_payloads_external",
                "suspension_event_not_daily_state",
            ),
        ),
    )


def _manifest(
    name: str,
    import_id: str,
    finished_at: datetime,
    date_range: tuple[date, date],
    universe: tuple[str, ...],
    primary_key: tuple[str, ...],
    availability_rule: str,
    units: tuple[str, ...],
    yearly: dict[int, dict[str, object]],
    artifacts: FileArtifacts,
    known_gaps: tuple[str, ...],
) -> DatasetManifest:
    hashes = {artifact: value[1] for artifact, value in artifacts[name].items()}
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.0.0",
        provider="tushare",
        source_endpoint="legacy-astramind-silver+tushare",
        request_identity=import_id,
        retrieved_at=finished_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=universe,
        primary_key=primary_key,
        availability_rule=availability_rule,
        units=units,
        row_count=sum(_integer(item.get(f"{name}_rows", 0)) for item in yearly.values()),
        artifact_hashes=hashes,
        known_gaps=known_gaps,
    )


def _daily_basic_gaps(cross_coverage: dict[str, int]) -> tuple[str, ...]:
    gaps = ["legacy_raw_payloads_external"]
    if cross_coverage["daily_rows_without_daily_basic"]:
        gaps.append("daily_rows_without_daily_basic")
    return tuple(gaps)


def _price_limit_gaps(
    yearly: dict[int, dict[str, object]],
    cross_coverage: dict[str, int],
) -> tuple[str, ...]:
    gaps = ["legacy_raw_payloads_external", "price_limits_before_2007_unavailable"]
    unusable = sum(_integer(item.get("unusable_limit_rows", 0)) for item in yearly.values())
    if unusable:
        gaps.append("rows_with_unusable_limit_prices")
    if cross_coverage["daily_rows_without_price_limit"]:
        gaps.append("daily_rows_without_price_limit")
    if cross_coverage["price_limit_rows_without_daily"]:
        gaps.append("price_limit_rows_without_daily_bar")
    return tuple(gaps)


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("年度覆盖统计不是整数")
    return value


__all__ = ["build_constraint_manifests"]
