"""Exact-path DuckDB queries for SW2021 hierarchy slices."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..contracts import IndustryHierarchyNode
from ..domain.rotation import IndustryCloseSeries


def snapshot_at(root: Path, identity: str) -> DataSnapshot:
    digest = identity.removeprefix("snapshot:sha256:")
    snapshot = DataSnapshot.model_validate_json(
        (root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
    )
    if snapshot.snapshot_id != identity:
        raise ValueError("DataSnapshot 身份与路径不一致")
    return snapshot


def snapshot_paths(root: Path, snapshot: DataSnapshot) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for reference in snapshot.datasets:
        digest = reference.dataset_version.removeprefix("sha256:")
        manifest_path = root / "datasets" / reference.dataset_name / digest / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        result[reference.dataset_name] = [
            str(manifest_path.parent / name)
            for name in manifest["artifact_paths"]
            if str(name).endswith(".parquet")
        ]
    return result


def has_l2(connection: duckdb.DuckDBPyConnection, taxonomy_paths: list[str]) -> bool:
    row = connection.execute(
        "SELECT count(*) FROM read_parquet(?) WHERE level = 'L2'",
        [taxonomy_paths],
    ).fetchone()
    return row is not None and int(row[0]) > 0


def taxonomy_nodes(
    connection: duckdb.DuckDBPyConnection,
    taxonomy_paths: list[str],
    *,
    level: Literal["L1", "L2"],
    parent_code: str | None,
) -> tuple[IndustryHierarchyNode, ...]:
    rows = connection.execute(
        """
        SELECT industry_code, industry_name, parent_code
        FROM read_parquet(?) WHERE level = ?
          AND is_published
          AND (? IS NULL OR parent_code = ?)
        ORDER BY industry_code
        """,
        [taxonomy_paths, level, parent_code, parent_code],
    ).fetchall()
    return tuple(
        IndustryHierarchyNode(code=str(code), name=str(name), level=level, parent_code=parent)
        for code, name, parent in rows
    )


def member_nodes(
    connection: duckdb.DuckDBPyConnection,
    membership_paths: list[str],
    security_paths: list[str],
    *,
    l2_code: str,
    as_of: date,
) -> tuple[IndustryHierarchyNode, ...]:
    rows = connection.execute(
        """
        SELECT DISTINCT m.instrument_id, coalesce(s.name, m.instrument_name)
        FROM read_parquet(?) m LEFT JOIN read_parquet(?) s USING (instrument_id)
        WHERE m.level = 'L2' AND m.industry_code = ?
          AND m.effective_from <= ?
          AND (m.effective_to IS NULL OR ? < m.effective_to)
          AND CAST(m.available_at AS DATE) <= ?
        ORDER BY m.instrument_id
        """,
        [membership_paths, security_paths, l2_code, as_of, as_of, as_of],
    ).fetchall()
    return tuple(
        IndustryHierarchyNode(code=str(code), name=str(name), level="stock", parent_code=l2_code)
        for code, name in rows
    )


def close_series(
    connection: duckdb.DuckDBPyConnection,
    paths: list[str],
    nodes: tuple[IndustryHierarchyNode, ...],
    *,
    as_of: date,
    stock: bool,
    allow_incomplete: bool = False,
    calendar_paths: list[str] | None = None,
) -> tuple[tuple[date, ...], tuple[IndustryCloseSeries, ...], tuple[str, ...]]:
    codes = [node.code for node in nodes]
    query = (
        """
        SELECT instrument_id, trade_date, close FROM read_parquet(?)
        WHERE instrument_id IN (SELECT unnest(?)) AND trade_date <= ?
        """
        if stock
        else """
        SELECT industry_code, trade_date, close FROM read_parquet(?)
        WHERE level = 'L2' AND industry_code IN (SELECT unnest(?)) AND trade_date <= ?
        """
    )
    rows = connection.execute(query, [paths, codes, as_of]).fetchall()
    values: dict[str, dict[date, float]] = {code: {} for code in codes}
    for code, day, close in rows:
        values[str(code)][day] = float(close)
    if calendar_paths:
        calendar_rows = connection.execute(
            """
            SELECT DISTINCT calendar_date FROM read_parquet(?)
            WHERE exchange = 'SSE' AND is_open AND calendar_date <= ?
            ORDER BY calendar_date DESC LIMIT 141
            """,
            [calendar_paths, as_of],
        ).fetchall()
        calendar = tuple(sorted(day for (day,) in calendar_rows))
    else:
        observed_dates = set().union(*(set(series) for series in values.values()))
        calendar = tuple(sorted(observed_dates))[-141:]
    if len(calendar) < 141:
        raise ValueError("同层对象参考交易日不足 141 日")
    required_dates = set(calendar)
    complete_codes = [code for code, series in values.items() if required_dates.issubset(series)]
    incomplete_codes = tuple(sorted(set(codes) - set(complete_codes)))
    if incomplete_codes and not allow_incomplete:
        raise ValueError("同层对象存在不足 141 日的历史")
    if len(complete_codes) < 3:
        raise ValueError("同层对象少于 3 个")
    names = {node.code: node.name for node in nodes}
    series = tuple(
        IndustryCloseSeries(
            industry_code=code,
            industry_name=names[code],
            closes={day: values[code][day] for day in calendar},
            constituent_counts={day: 3 for day in calendar},
        )
        for code in complete_codes
    )
    return calendar, series, incomplete_codes


__all__ = [
    "close_series",
    "has_l2",
    "member_nodes",
    "snapshot_at",
    "snapshot_paths",
    "taxonomy_nodes",
]
