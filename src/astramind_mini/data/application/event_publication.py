"""Manifest construction for point-in-time tactical event datasets."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..contracts import DatasetManifest
from .datasets import build_dataset_manifest_from_hashes
from .historical_publication import FileArtifacts
from .identity import canonical_json, file_hash
from .state_files import write_bytes_atomic


def build_event_manifests(
    *,
    import_id: str,
    start_date: date,
    end_date: date,
    annual: dict[str, dict[int, dict[str, object]]],
    staging: Path,
    retrieved_at: datetime,
) -> tuple[tuple[DatasetManifest, ...], FileArtifacts]:
    artifacts: FileArtifacts = {name: {} for name in annual}
    for name, years in annual.items():
        for year, item in sorted(years.items()):
            path = Path(str(item["path"]))
            artifacts[name][f"{name}-{year}.parquet"] = (path, str(item["hash"]))
        coverage_path = staging / f"{name}-coverage.json"
        write_bytes_atomic(
            coverage_path,
            canonical_json(
                {
                    "dataset_name": name,
                    "date_range": [start_date, end_date],
                    "annual": years,
                    "rows": sum(_integer(item["rows"]) for item in years.values()),
                }
            ),
        )
        artifacts[name]["coverage.json"] = (coverage_path, file_hash(coverage_path))
    manifests = tuple(
        _manifest(
            name=name,
            import_id=import_id,
            start_date=start_date,
            end_date=end_date,
            retrieved_at=retrieved_at,
            artifacts=artifacts,
            annual=annual[name],
        )
        for name in ("lhb_event", "lhb_seat", "shareholder_count")
    )
    return manifests, artifacts


def _manifest(
    *,
    name: str,
    import_id: str,
    start_date: date,
    end_date: date,
    retrieved_at: datetime,
    artifacts: FileArtifacts,
    annual: dict[int, dict[str, object]],
) -> DatasetManifest:
    definitions = {
        "lhb_event": {
            "endpoint": "top_list",
            "primary_key": ("source_record_hash",),
            "availability": "trade_date 18:00 Asia/Shanghai",
            "units": ("price:CNY", "amount:ten_thousand_CNY", "rate:percent"),
        },
        "lhb_seat": {
            "endpoint": "top_inst",
            "primary_key": ("source_record_hash",),
            "availability": "trade_date 18:00 Asia/Shanghai",
            "units": ("amount:CNY", "rate:percent"),
        },
        "shareholder_count": {
            "endpoint": "stk_holdernumber",
            "primary_key": ("source_record_hash",),
            "availability": "announced_on 18:00 Asia/Shanghai",
            "units": ("holder_count:household",),
        },
    }
    definition = definitions[name]
    null_holder_rows = sum(
        _integer(item.get("null_holder_count_rows", 0)) for item in annual.values()
    )
    early_announcement_rows = sum(
        _integer(item.get("announcement_before_period_rows", 0)) for item in annual.values()
    )
    gaps = []
    if null_holder_rows:
        gaps.append("rows_with_unknown_holder_count")
    if early_announcement_rows:
        gaps.append("announcement_precedes_reporting_period")
    observed_starts = [
        date.fromisoformat(str(item["start_date"]))
        for item in annual.values()
        if item.get("start_date") is not None
    ]
    if not observed_starts:
        gaps.append("no_observations_in_requested_range")
    elif (observed_start := min(observed_starts)).year > start_date.year:
        gaps.append(
            "provider_empty_years_before_first_observation:"
            f"{start_date.year}-{observed_start.year - 1}"
        )
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.0.0",
        provider="tushare",
        source_endpoint=str(definition["endpoint"]),
        request_identity=import_id,
        retrieved_at=retrieved_at,
        market_timezone="Asia/Shanghai",
        date_range=(start_date, end_date),
        universe=(),
        primary_key=tuple(definition["primary_key"]),
        availability_rule=str(definition["availability"]),
        units=tuple(definition["units"]),
        row_count=sum(_integer(item["rows"]) for item in annual.values()),
        artifact_hashes={key: value[1] for key, value in artifacts[name].items()},
        known_gaps=tuple(gaps),
    )


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("事件年度统计不是整数")
    return value


__all__ = ["build_event_manifests"]
