"""Constants and data-quality helpers for the industry foundation backfill."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

TAXONOMY_FIELDS = (
    "index_code",
    "industry_name",
    "level",
    "industry_code",
    "is_pub",
    "parent_code",
    "src",
)
MEMBERSHIP_FIELDS = (
    "l1_code",
    "l1_name",
    "l2_code",
    "l2_name",
    "l3_code",
    "l3_name",
    "ts_code",
    "name",
    "in_date",
    "out_date",
    "is_new",
)
INDEX_DAILY_FIELDS = (
    "ts_code",
    "trade_date",
    "name",
    "open",
    "low",
    "high",
    "close",
    "change",
    "pct_change",
    "vol",
    "amount",
    "pe",
    "pb",
    "float_mv",
    "total_mv",
)


@dataclass(frozen=True, slots=True)
class IndustryArtifacts:
    taxonomy_path: Path
    membership_path: Path
    daily_path: Path
    taxonomy_rows: int
    membership_stats: dict[str, object]
    daily_stats: dict[str, object]


def five_year_windows(start: date, end: date) -> tuple[tuple[date, date], ...]:
    result = []
    current = start
    while current <= end:
        window_end = min(end, date(min(current.year + 4, end.year), 12, 31))
        result.append((current, window_end))
        current = date(window_end.year + 1, 1, 1)
    return tuple(result)


def membership_overlap_stats(path: Path) -> dict[str, int]:
    with duckdb.connect(":memory:") as connection:
        row = connection.execute(
            """
            WITH intervals AS (
              SELECT industry_code, instrument_id, effective_from, effective_to,
                     lead(industry_code) OVER (
                       PARTITION BY instrument_id
                       ORDER BY effective_from, coalesce(effective_to, DATE '9999-12-31')
                     ) AS next_code,
                     lead(effective_from) OVER (
                       PARTITION BY instrument_id
                       ORDER BY effective_from, coalesce(effective_to, DATE '9999-12-31')
                     ) AS next_start
              FROM read_parquet(?)
            )
            SELECT count(*) FILTER (WHERE industry_code = next_code),
                   count(*) FILTER (WHERE industry_code <> next_code)
            FROM intervals
            WHERE effective_to IS NOT NULL
              AND next_start IS NOT NULL
              AND effective_to > next_start
            """,
            [str(path)],
        ).fetchone()
    assert row is not None
    same_industry, cross_industry = int(row[0]), int(row[1])
    if cross_industry:
        raise ValueError(f"行业成员存在 {cross_industry} 个跨行业重叠区间")
    return {"same_industry_overlap_rows": same_industry}


__all__ = [
    "INDEX_DAILY_FIELDS",
    "MEMBERSHIP_FIELDS",
    "TAXONOMY_FIELDS",
    "IndustryArtifacts",
    "five_year_windows",
    "membership_overlap_stats",
]
