"""Manifest and coverage artifacts for WP-0002B-H3."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..contracts import DatasetManifest
from ..ports import LegacyMarketRelease
from .datasets import build_dataset_manifest_from_hashes
from .historical_publication import FileArtifacts
from .identity import canonical_json, file_hash
from .state_files import write_bytes_atomic


def build_status_manifests(
    *,
    base: dict[str, DatasetManifest],
    release: LegacyMarketRelease,
    import_id: str,
    name_path: Path,
    name_stats: dict[str, int],
    yearly: dict[int, dict[str, object]],
    staging: Path,
    finished_at: datetime,
) -> tuple[tuple[DatasetManifest, ...], FileArtifacts]:
    artifacts: FileArtifacts = {
        "security_name_history": {
            "security-name-history.parquet": (name_path, file_hash(name_path))
        },
        "daily_tradability": {},
    }
    for year, item in sorted(yearly.items()):
        path = Path(str(item["path"]))
        artifacts["daily_tradability"][f"daily-tradability-{year}.parquet"] = (
            path,
            str(item["hash"]),
        )
    coverage = {
        "name_history": name_stats,
        "annual": yearly,
        "totals": _totals(yearly),
        "source_dataset_version": release.dataset_version,
    }
    for name in artifacts:
        path = staging / f"{name}-coverage.json"
        write_bytes_atomic(
            path,
            canonical_json({"dataset_name": name, **coverage}),
        )
        artifacts[name]["coverage.json"] = (path, file_hash(path))
    date_range = base["daily_market"].date_range
    universe = base["security_master"].universe
    manifests = (
        _manifest(
            name="security_name_history",
            provider="tushare",
            endpoint="legacy-astramind-silver/namechange",
            import_id=import_id,
            finished_at=finished_at,
            date_range=(date(1990, 12, 1), date_range[1]),
            universe=universe,
            primary_key=("instrument_id", "effective_start_date", "name"),
            availability_rule="effective_start_date 18:00 Asia/Shanghai",
            row_count=name_stats["rows"],
            artifacts=artifacts,
            gaps=_name_gaps(name_stats),
        ),
        _manifest(
            name="daily_tradability",
            provider="derived",
            endpoint="versioned-market-state-projection",
            import_id=import_id,
            finished_at=finished_at,
            date_range=date_range,
            universe=universe,
            primary_key=("instrument_id", "trade_date"),
            availability_rule="trade_date 18:00 Asia/Shanghai; ex-post constraint evidence",
            row_count=_totals(yearly)["rows"],
            artifacts=artifacts,
            gaps=_tradability_gaps(yearly),
        ),
    )
    return manifests, artifacts


def _manifest(
    *,
    name: str,
    provider: str,
    endpoint: str,
    import_id: str,
    finished_at: datetime,
    date_range: tuple[date, date],
    universe: tuple[str, ...],
    primary_key: tuple[str, ...],
    availability_rule: str,
    row_count: int,
    artifacts: FileArtifacts,
    gaps: tuple[str, ...],
) -> DatasetManifest:
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.0.0",
        provider=provider,
        source_endpoint=endpoint,
        request_identity=import_id,
        retrieved_at=finished_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=universe,
        primary_key=primary_key,
        availability_rule=availability_rule,
        units=(),
        row_count=row_count,
        artifact_hashes={key: value[1] for key, value in artifacts[name].items()},
        known_gaps=gaps,
    )


def _totals(yearly: dict[int, dict[str, object]]) -> dict[str, int]:
    keys = (
        "rows",
        "unknown_name_rows",
        "special_treatment_rows",
        "rows_with_daily_bar",
        "confirmed_suspended_rows",
        "ambiguous_event_rows",
        "unknown_no_bar_rows",
        "missing_limit_rows",
        "unusable_limit_rows",
        "upper_limit_locked_rows",
        "lower_limit_locked_rows",
    )
    return {key: sum(_integer(item[key]) for item in yearly.values()) for key in keys}


def _name_gaps(stats: dict[str, int]) -> tuple[str, ...]:
    gaps = ["legacy_raw_payloads_external"]
    if stats["adjusted_intervals"]:
        gaps.append("open_intervals_closed_at_next_name_start")
    return tuple(gaps)


def _tradability_gaps(yearly: dict[int, dict[str, object]]) -> tuple[str, ...]:
    totals = _totals(yearly)
    gaps = ["price_limits_before_2007_unavailable"]
    if totals["unknown_name_rows"]:
        gaps.append("name_status_unknown_for_some_listed_days")
    if totals["unknown_no_bar_rows"]:
        gaps.append("listed_days_without_bar_or_suspension_evidence")
    if totals["ambiguous_event_rows"]:
        gaps.append("ambiguous_suspension_events")
    if totals["unusable_limit_rows"]:
        gaps.append("rows_with_unusable_limit_prices")
    return tuple(gaps)


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("年度投影统计不是整数")
    return value


__all__ = ["build_status_manifests"]
