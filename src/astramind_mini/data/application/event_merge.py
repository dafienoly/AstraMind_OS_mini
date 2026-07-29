"""Merge exact tactical-event dataset versions without scanning mutable latest data."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb

from ..contracts import DatasetManifest
from .event_backfill_support import artifact_paths
from .identity import file_hash

EVENT_DATASETS = ("lhb_event", "lhb_seat", "shareholder_count")
_DEFINITIONS = {
    "lhb_event": (
        ("trade_date", "instrument_id", "source_record_hash"),
        "trade_date",
    ),
    "lhb_seat": (
        ("trade_date", "instrument_id", "source_record_hash"),
        "trade_date",
    ),
    "shareholder_count": (
        ("announced_on", "instrument_id", "reporting_period", "source_record_hash"),
        "announced_on",
    ),
}


def load_current_event_manifests(root: Path) -> dict[str, DatasetManifest]:
    result: dict[str, DatasetManifest] = {}
    for name in EVENT_DATASETS:
        pointer = root / "current" / f"{name}.json"
        if not pointer.is_file():
            continue
        value = json.loads(pointer.read_text(encoding="utf-8"))
        manifest_path = root / str(value.get("manifest_path", ""))
        manifest = DatasetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if manifest.dataset_name != name or manifest.dataset_version != value.get(
            "dataset_version"
        ):
            raise ValueError(f"{name} 当前指针与清单身份冲突")
        result[name] = manifest
    if result and set(result) != set(EVENT_DATASETS):
        raise ValueError("事件数据 current 指针不完整")
    return result


def merge_event_annual(
    *,
    root: Path,
    base: dict[str, DatasetManifest],
    incremental: dict[str, dict[int, dict[str, object]]],
    staging: Path,
) -> dict[str, dict[int, dict[str, object]]]:
    result: dict[str, dict[int, dict[str, object]]] = {}
    for name in EVENT_DATASETS:
        existing = _year_paths(root, base.get(name))
        increments = {year: Path(str(item["path"])) for year, item in incremental[name].items()}
        result[name] = {}
        for year in sorted(set(existing) | set(increments)):
            if year in existing and year in increments:
                path = staging / "merged" / f"{name}-{year}.parquet"
                _merge_files(name, (existing[year], increments[year]), path)
            else:
                selected = existing.get(year, increments.get(year))
                assert selected is not None
                path = selected
            result[name][year] = {"path": str(path), "hash": file_hash(path), **_stats(name, path)}
    return result


def combined_date_range(
    base: dict[str, DatasetManifest],
    start_date: date,
    end_date: date,
) -> tuple[date, date]:
    starts = [start_date, *(item.date_range[0] for item in base.values())]
    ends = [end_date, *(item.date_range[1] for item in base.values())]
    return min(starts), max(ends)


def _year_paths(root: Path, manifest: DatasetManifest | None) -> dict[int, Path]:
    if manifest is None:
        return {}
    result = {}
    for path in artifact_paths(root, manifest):
        stem = path.stem
        try:
            year = int(stem.rsplit("-", 1)[-1])
        except ValueError as error:
            raise ValueError(f"{manifest.dataset_name} 年度制品命名无效：{path.name}") from error
        result[year] = path
    return result


def _merge_files(name: str, sources: tuple[Path, ...], output: Path) -> None:
    ordering, _ = _DEFINITIONS[name]
    order_sql = ", ".join(f'"{column}"' for column in ordering)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?)
              QUALIFY row_number() OVER (
                PARTITION BY source_record_hash ORDER BY retrieved_at DESC
              ) = 1
              ORDER BY {order_sql}
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [[str(path) for path in sources]],
        )
    temporary.replace(output)


def _stats(name: str, path: Path) -> dict[str, object]:
    _, date_column = _DEFINITIONS[name]
    with duckdb.connect(":memory:") as connection:
        row = connection.execute(
            f"""
            SELECT count(*), count(DISTINCT source_record_hash),
                   min("{date_column}"), max("{date_column}")
            FROM read_parquet(?)
            """,
            [str(path)],
        ).fetchone()
        assert row is not None
        if int(row[0]) != int(row[1]):
            raise ValueError(f"{name} 合并后观察身份重复")
        result: dict[str, object] = {
            "rows": int(row[0]),
            "unique_rows": int(row[1]),
            "start_date": row[2].isoformat() if row[2] else None,
            "end_date": row[3].isoformat() if row[3] else None,
        }
        if name == "shareholder_count":
            holder = connection.execute(
                """
                SELECT count(*) FILTER (WHERE holder_count IS NULL),
                       count(*) FILTER (WHERE announced_on < reporting_period)
                FROM read_parquet(?)
                """,
                [str(path)],
            ).fetchone()
            assert holder is not None
            result["null_holder_count_rows"] = int(holder[0])
            result["announcement_before_period_rows"] = int(holder[1])
        return result


__all__ = [
    "EVENT_DATASETS",
    "combined_date_range",
    "load_current_event_manifests",
    "merge_event_annual",
]
