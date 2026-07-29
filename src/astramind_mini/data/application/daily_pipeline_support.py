"""Exact-snapshot helpers for the WP-0025 daily industry increment."""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import cast

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest
from .datasets import build_dataset_manifest_from_hashes
from .identity import file_hash
from .provider_lineage import market_source_attribution


def load_snapshot_bundle(
    root: Path, snapshot_id: str
) -> tuple[DataSnapshot, dict[str, DatasetManifest], dict[str, tuple[Path, ...]]]:
    digest = _digest(snapshot_id, "snapshot:sha256")
    snapshot = DataSnapshot.model_validate_json(
        (root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
    )
    if snapshot.snapshot_id != snapshot_id:
        raise ValueError("日度管线基础快照身份冲突")
    manifests: dict[str, DatasetManifest] = {}
    paths: dict[str, tuple[Path, ...]] = {}
    for reference in snapshot.datasets:
        dataset_digest = _digest(reference.dataset_version, "sha256")
        directory = root / "datasets" / reference.dataset_name / dataset_digest
        manifest = DatasetManifest.model_validate_json(
            (directory / "manifest.json").read_text(encoding="utf-8")
        )
        if (
            manifest.dataset_version != reference.dataset_version
            or manifest.content_hash != reference.content_hash
        ):
            raise ValueError(f"基础快照数据集身份冲突：{reference.dataset_name}")
        artifacts = tuple(
            directory / name for name in manifest.artifact_paths if name.endswith(".parquet")
        )
        if not artifacts or any(not path.is_file() for path in artifacts):
            raise ValueError(f"基础快照数据集制品缺失：{reference.dataset_name}")
        manifests[reference.dataset_name] = manifest
        paths[reference.dataset_name] = artifacts
    return snapshot, manifests, paths


def published_industries(
    taxonomy_paths: tuple[Path, ...],
) -> tuple[tuple[str, str, str], ...]:
    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            """
            SELECT level, industry_code, industry_name
            FROM read_parquet(?)
            WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021'
              AND (level = 'L1' OR (level = 'L2' AND is_published))
            ORDER BY level, industry_code
            """,
            [[str(path) for path in taxonomy_paths]],
        ).fetchall()
    result = tuple((str(level), str(code), str(name)) for level, code, name in rows)
    l1_count = sum(level == "L1" for level, _, _ in result)
    if l1_count != 31:
        raise ValueError(f"日度管线要求 31 个 L1，实际 {l1_count}")
    if not any(level == "L2" for level, _, _ in result):
        raise ValueError("日度管线没有已发布 L2 指数")
    return result


def merge_industry_daily(
    *,
    base_paths: tuple[Path, ...],
    increments: tuple[Path, ...],
    target_date: date,
    output: Path,
    expected_l1: int,
    expected_l2: int,
) -> tuple[int, date, date]:
    if not increments:
        raise ValueError("日度行业增量为空")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?) WHERE trade_date <> ?
              UNION ALL
              SELECT * FROM read_parquet(?)
              ORDER BY level, industry_code, trade_date
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [
                [str(path) for path in base_paths],
                target_date,
                [str(path) for path in increments],
            ],
        )
        coverage = connection.execute(
            """
            SELECT
              count(DISTINCT industry_code) FILTER (WHERE level = 'L1'),
              count(DISTINCT industry_code) FILTER (WHERE level = 'L2'),
              count(*),
              min(trade_date),
              max(trade_date),
              count(*) - count(DISTINCT (level, industry_code, trade_date))
            FROM read_parquet(?)
            WHERE trade_date = ?
            """,
            [str(temporary), target_date],
        ).fetchone()
        totals = connection.execute(
            "SELECT count(*), min(trade_date), max(trade_date) FROM read_parquet(?)",
            [str(temporary)],
        ).fetchone()
    assert coverage is not None and totals is not None
    if (int(coverage[0]), int(coverage[1])) != (expected_l1, expected_l2):
        temporary.unlink(missing_ok=True)
        raise ValueError(
            "目标交易日行业覆盖不完整："
            f"L1={coverage[0]}/{expected_l1},L2={coverage[1]}/{expected_l2}"
        )
    if int(coverage[5]):
        temporary.unlink(missing_ok=True)
        raise ValueError("目标交易日行业日线存在重复身份")
    temporary.replace(output)
    return int(totals[0]), cast(date, totals[1]), cast(date, totals[2])


def merge_trade_calendar(
    *,
    base_paths: tuple[Path, ...],
    increment: Path,
    replace_from: date,
    output: Path,
) -> tuple[int, date, date]:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?) WHERE calendar_date < ?
              UNION ALL
              SELECT * FROM read_parquet(?)
              ORDER BY exchange, calendar_date
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [[str(path) for path in base_paths], replace_from, str(increment)],
        )
        row = connection.execute(
            """
            SELECT count(*), min(calendar_date), max(calendar_date),
                   count(*) - count(DISTINCT (exchange, calendar_date))
            FROM read_parquet(?)
            """,
            [str(temporary)],
        ).fetchone()
    assert row is not None
    if int(row[3]):
        temporary.unlink(missing_ok=True)
        raise ValueError("增量交易日历存在重复身份")
    temporary.replace(output)
    return int(row[0]), cast(date, row[1]), cast(date, row[2])


def merge_broad_index_daily(
    *,
    base_paths: tuple[Path, ...],
    increment: Path,
    target_date: date,
    output: Path,
) -> tuple[int, date, date]:
    if not increment.is_file():
        raise ValueError("日度宽基指数增量为空")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?) WHERE trade_date <> ?
              UNION ALL
              SELECT * FROM read_parquet(?)
              ORDER BY instrument_id, trade_date
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [[str(path) for path in base_paths], target_date, str(increment)],
        )
        coverage = connection.execute(
            """
            SELECT count(DISTINCT instrument_id),
                   count(*) - count(DISTINCT (instrument_id, trade_date))
            FROM read_parquet(?) WHERE trade_date = ?
            """,
            [str(temporary), target_date],
        ).fetchone()
        totals = connection.execute(
            "SELECT count(*), min(trade_date), max(trade_date) FROM read_parquet(?)",
            [str(temporary)],
        ).fetchone()
    assert coverage is not None and totals is not None
    if int(coverage[0]) != 6 or int(coverage[1]):
        temporary.unlink(missing_ok=True)
        raise ValueError(f"目标交易日宽基指数覆盖不完整：{coverage[0]}/6")
    temporary.replace(output)
    return int(totals[0]), cast(date, totals[1]), cast(date, totals[2])


def daily_industry_manifest(
    *,
    path: Path,
    run_id: str,
    retrieved_at: datetime,
    row_count: int,
    date_range: tuple[date, date],
) -> DatasetManifest:
    attribution = market_source_attribution((path,))
    return build_dataset_manifest_from_hashes(
        dataset_name="industry_index_daily",
        schema_version="1.0.0",
        provider=attribution.provider,
        source_endpoint=attribution.source_endpoint,
        request_identity="sha256:" + run_id.rsplit(":", 1)[-1],
        retrieved_at=retrieved_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=(),
        primary_key=("level", "industry_code", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=(
            "levels:L1,L2",
            "price:index_points",
            "valuation:provider_native",
            "volume:provider_native_unverified",
            "amount:provider_native_unverified",
        ),
        row_count=row_count,
        artifact_hashes={"industry_index_daily.parquet": file_hash(path)},
        known_gaps=(
            "provider_native_volume_amount_market_value_units_unverified",
            "provider_ohlc_rounding_tolerance_up_to_1bp",
        ),
        provider_lineage=attribution.provider_lineage,
    )


def daily_calendar_manifest(
    *,
    path: Path,
    run_id: str,
    retrieved_at: datetime,
    row_count: int,
    date_range: tuple[date, date],
) -> DatasetManifest:
    attribution = market_source_attribution((path,), date_column="calendar_date")
    return build_dataset_manifest_from_hashes(
        dataset_name="trade_calendar",
        schema_version="1.0.0",
        provider=attribution.provider,
        source_endpoint=attribution.source_endpoint,
        request_identity="sha256:" + run_id.rsplit(":", 1)[-1],
        retrieved_at=retrieved_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=("SSE",),
        primary_key=("exchange", "calendar_date"),
        availability_rule="provider schedule known at retrieved_at",
        units=("calendar_date:date", "is_open:boolean"),
        row_count=row_count,
        artifact_hashes={"trade_calendar.parquet": file_hash(path)},
        provider_lineage=attribution.provider_lineage,
    )


def daily_broad_index_manifest(
    *,
    path: Path,
    run_id: str,
    retrieved_at: datetime,
    row_count: int,
    date_range: tuple[date, date],
) -> DatasetManifest:
    attribution = market_source_attribution((path,))
    return build_dataset_manifest_from_hashes(
        dataset_name="broad_index_daily",
        schema_version="1.0.0",
        provider=attribution.provider,
        source_endpoint=attribution.source_endpoint,
        request_identity="sha256:" + run_id.rsplit(":", 1)[-1],
        retrieved_at=retrieved_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=(
            "000001.SH",
            "000300.SH",
            "000688.SH",
            "000852.SH",
            "399001.SZ",
            "399006.SZ",
        ),
        primary_key=("instrument_id", "trade_date"),
        availability_rule="trade_date 18:00 Asia/Shanghai",
        units=(
            "price:index_points",
            "volume:lots",
            "amount:CNY",
            "percent_change:percent",
        ),
        row_count=row_count,
        artifact_hashes={"broad_index_daily.parquet": file_hash(path)},
        provider_lineage=attribution.provider_lineage,
    )


def checkpoint_file(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("日度请求检查点无效")
    return value


def _digest(identity: str, prefix: str) -> str:
    value = identity.removeprefix(prefix + ":")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


__all__ = [
    "checkpoint_file",
    "daily_broad_index_manifest",
    "daily_calendar_manifest",
    "daily_industry_manifest",
    "load_snapshot_bundle",
    "merge_broad_index_daily",
    "merge_industry_daily",
    "merge_trade_calendar",
    "published_industries",
]
