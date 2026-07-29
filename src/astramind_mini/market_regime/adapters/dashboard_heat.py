"""Industry-heat query over exact immutable dataset paths."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import duckdb

from ..contracts.dashboard import IndustryHeatRow


def industry_heat(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, tuple[Path, ...]],
    cutoff: date,
) -> tuple[IndustryHeatRow, ...]:
    index_paths = [str(item) for item in paths["industry_index_daily"]]
    membership_paths = [str(item) for item in paths["industry_membership"]]
    market_paths = [str(item) for item in paths["daily_market"]]
    rows = connection.execute(
        """
        WITH index_history AS (
          SELECT *,
            row_number() OVER (
              PARTITION BY industry_code ORDER BY trade_date DESC
            ) AS recent_rank
          FROM read_parquet(?)
          WHERE level = 'L1' AND trade_date <= ?
        ), index_metrics AS (
          SELECT industry_code,
            max(industry_name) FILTER (WHERE recent_rank = 1) AS industry_name,
            max(trade_date) FILTER (WHERE recent_rank = 1) AS trade_date,
            max(percent_change) FILTER (WHERE recent_rank = 1) AS percent_change,
            max(amount_provider_native) FILTER (WHERE recent_rank = 1) AS latest_amount,
            avg(amount_provider_native) FILTER (
              WHERE recent_rank BETWEEN 2 AND 21
            ) AS amount_average,
            stddev_samp(percent_change) FILTER (
              WHERE recent_rank BETWEEN 1 AND 20
            ) AS volatility_20d,
            max(price_earnings) FILTER (WHERE recent_rank = 1) AS price_earnings,
            max(price_book) FILTER (WHERE recent_rank = 1) AS price_book
          FROM index_history WHERE recent_rank <= 21 GROUP BY industry_code
        ), benchmark AS (
          SELECT avg(percent_change) AS average_return FROM index_metrics
        ), members AS (
          SELECT industry_code, instrument_id, instrument_name
          FROM read_parquet(?)
          WHERE level = 'L1' AND effective_from <= ?
            AND (effective_to IS NULL OR ? < effective_to)
            AND CAST(available_at AS DATE) <= ?
          QUALIFY row_number() OVER (
            PARTITION BY industry_code, instrument_id
            ORDER BY retrieved_at DESC, effective_from DESC
          ) = 1
        ), daily_today AS (
          SELECT instrument_id, percent_change
          FROM read_parquet(?) WHERE trade_date = ?
        ), member_market AS (
          SELECT m.*, d.percent_change
          FROM members m LEFT JOIN daily_today d USING (instrument_id)
        ), member_metrics AS (
          SELECT industry_code,
            count(*) AS member_count,
            count(percent_change) AS covered_count,
            count(*) FILTER (WHERE percent_change > 0) AS advancing,
            count(*) FILTER (WHERE percent_change < 0) AS declining
          FROM member_market GROUP BY industry_code
        ), leaders AS (
          SELECT industry_code, instrument_id, instrument_name, percent_change
          FROM member_market WHERE percent_change IS NOT NULL
          QUALIFY row_number() OVER (
            PARTITION BY industry_code ORDER BY percent_change DESC, instrument_id
          ) = 1
        )
        SELECT i.*, i.percent_change - b.average_return AS relative_strength,
          m.member_count, m.covered_count, m.advancing, m.declining,
          l.instrument_id, l.instrument_name, l.percent_change
        FROM index_metrics i CROSS JOIN benchmark b
        LEFT JOIN member_metrics m USING (industry_code)
        LEFT JOIN leaders l USING (industry_code)
        ORDER BY relative_strength DESC, i.industry_code
        """,
        [
            index_paths,
            cutoff,
            membership_paths,
            cutoff,
            cutoff,
            cutoff,
            market_paths,
            cutoff,
        ],
    ).fetchall()
    return tuple(_to_heat_row(row) for row in rows)


def _to_heat_row(row: tuple[Any, ...]) -> IndustryHeatRow:
    member_count = int(row[10] or 0)
    covered = int(row[11] or 0)
    advancing = int(row[12] or 0)
    declining = int(row[13] or 0)
    compared = advancing + declining
    coverage = covered / member_count if member_count else 0
    latest_amount = float(row[4]) if row[4] is not None else None
    average_amount = float(row[5]) if row[5] is not None else None
    return IndustryHeatRow(
        industry_code=str(row[0]),
        industry_name=str(row[1]),
        trade_date=row[2],
        percent_change=float(row[3]),
        relative_strength=float(row[9]),
        breadth_ratio=advancing / compared if compared else None,
        advancing=advancing,
        declining=declining,
        member_count=member_count,
        covered_member_count=covered,
        coverage_ratio=coverage,
        amount_change_20d=(
            latest_amount / average_amount - 1
            if latest_amount is not None and average_amount
            else None
        ),
        volatility_20d=float(row[6]) if row[6] is not None else None,
        price_earnings=float(row[7]) if row[7] is not None else None,
        price_book=float(row[8]) if row[8] is not None else None,
        leading_instrument_id=str(row[14]) if row[14] is not None else None,
        leading_instrument_name=str(row[15]) if row[15] is not None else None,
        leading_percent_change=float(row[16]) if row[16] is not None else None,
        known_gaps=(() if coverage >= 0.9 else ("industry_member_market_coverage_below_90pct",)),
    )


__all__ = ["industry_heat"]
