"""Cross-dataset coverage evidence for WP-0002B-H2."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from ..contracts import DatasetManifest


def constraint_cross_coverage(
    *,
    data_root: Path,
    base: dict[str, DatasetManifest],
    yearly: dict[int, dict[str, object]],
    price_start: date,
) -> dict[str, int]:
    daily = _published_paths(data_root, base["daily_market"])
    daily_basic = _yearly_paths(yearly, "daily_basic")
    price_limit = _yearly_paths(yearly, "price_limit")
    with duckdb.connect(":memory:") as connection:
        daily_without_basic = _anti_count(connection, daily, daily_basic)
        basic_without_daily = _anti_count(connection, daily_basic, daily)
        daily_without_limit = connection.execute(
            """
            SELECT count(*) FROM read_parquet(?) daily
            ANTI JOIN read_parquet(?) limits USING (instrument_id, trade_date)
            WHERE daily.trade_date >= ?
            """,
            [daily, price_limit, price_start],
        ).fetchone()
        limit_without_daily = _anti_count(connection, price_limit, daily)
    assert daily_without_limit is not None
    return {
        "daily_rows_without_daily_basic": daily_without_basic,
        "daily_basic_rows_without_daily": basic_without_daily,
        "daily_rows_without_price_limit": int(daily_without_limit[0]),
        "price_limit_rows_without_daily": limit_without_daily,
    }


def _published_paths(root: Path, manifest: DatasetManifest) -> list[str]:
    digest = manifest.dataset_version.rsplit(":", 1)[-1]
    directory = root / "datasets" / manifest.dataset_name / digest
    return [str(directory / name) for name in manifest.artifact_paths if name.endswith(".parquet")]


def _yearly_paths(yearly: dict[int, dict[str, object]], dataset: str) -> list[str]:
    key = f"{dataset}_path"
    return [str(item[key]) for _, item in sorted(yearly.items()) if key in item]


def _anti_count(
    connection: duckdb.DuckDBPyConnection,
    left: list[str],
    right: list[str],
) -> int:
    row = connection.execute(
        """
        SELECT count(*) FROM read_parquet(?) left_rows
        ANTI JOIN read_parquet(?) right_rows USING (instrument_id, trade_date)
        """,
        [left, right],
    ).fetchone()
    assert row is not None
    return int(row[0])


__all__ = ["constraint_cross_coverage"]
