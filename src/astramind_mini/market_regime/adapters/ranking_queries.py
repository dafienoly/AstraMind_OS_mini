"""Bounded point-in-time queries used by the industry research ranking."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb

from ..domain.research_ranking import RankingFeature


def ranking_features(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
    *,
    cutoff: date,
) -> tuple[RankingFeature, ...]:
    _optional_sources(connection, paths)
    rows = connection.execute(
        """
        WITH eligible AS (
          SELECT instrument_id FROM read_parquet(?) WHERE trade_date = ?
            AND research_eligibility = 'eligible' AND has_daily_bar
        ), members AS (
          SELECT m.instrument_id, m.instrument_name, m.industry_code, m.effective_from
          FROM read_parquet(?) m JOIN eligible e USING (instrument_id)
          WHERE m.taxonomy = 'SW' AND m.level = 'L1'
            AND m.effective_from <= ?
            AND (m.effective_to IS NULL OR ? < m.effective_to)
            AND CAST(m.available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
        ), ranked_bars AS (
          SELECT a.instrument_id, a.trade_date, a.research_close_index close_value,
                 a.reported_total_return daily_return,
                 row_number() OVER (
                   PARTITION BY a.instrument_id ORDER BY a.trade_date DESC
                 ) rn
          FROM read_parquet(?) a JOIN members m USING (instrument_id)
          WHERE a.trade_date <= ?
        ), bar_features AS (
          SELECT instrument_id,
            arg_max(close_value, trade_date) / nullif(max(close_value) FILTER (rn = 2), 0) - 1 r1,
            arg_max(close_value, trade_date) / nullif(max(close_value) FILTER (rn = 6), 0) - 1 r5,
            arg_max(close_value, trade_date) / nullif(max(close_value) FILTER (rn = 21), 0) - 1 r20,
            arg_max(close_value, trade_date) / nullif(max(close_value) FILTER (rn = 61), 0) - 1 r60,
            (arg_max(close_value, trade_date) - min(close_value) FILTER (rn <= 120))
              / nullif(max(close_value) FILTER (rn <= 120)
                - min(close_value) FILTER (rn <= 120), 0) position120,
            stddev_samp(daily_return) FILTER (rn BETWEEN 2 AND 21) volatility20,
            stddev_samp(daily_return) FILTER (
              rn BETWEEN 2 AND 21 AND daily_return < 0
            ) downside20,
            arg_max(close_value, trade_date)
              / nullif(max(close_value) FILTER (rn <= 60), 0) - 1 dd60,
            CAST(arg_max(close_value, trade_date)
              < avg(close_value) FILTER (rn <= 5) AS INTEGER)
              + CAST(arg_max(close_value, trade_date)
                < avg(close_value) FILTER (rn <= 10) AS INTEGER)
              + CAST(arg_max(close_value, trade_date)
                < avg(close_value) FILTER (rn <= 20) AS INTEGER) below_ma
          FROM ranked_bars WHERE rn <= 120 GROUP BY instrument_id
        ), latest AS (
          SELECT m.instrument_id, m.instrument_name, m.industry_code, m.effective_from,
                 d.turnover_rate, d.price_earnings_ttm, d.price_book,
                 d.dividend_yield_ttm,
                 dm.amount_thousand_cny
                   / nullif(sum(dm.amount_thousand_cny) OVER (), 0) amount_share
          FROM members m
          LEFT JOIN read_parquet(?) d ON d.instrument_id = m.instrument_id
            AND d.trade_date = ?
          LEFT JOIN read_parquet(?) dm ON dm.instrument_id = m.instrument_id
            AND dm.trade_date = ?
        ), lhb AS (
          SELECT instrument_id, least(count(*) / 3.0, 1.0) attention
          FROM lhb_source
          WHERE trade_date BETWEEN ? - INTERVAL 35 DAY AND ?
            AND CAST(available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
          GROUP BY instrument_id
        ), holders AS (
          SELECT instrument_id,
                 (max(holder_count) FILTER (rn = 1)
                   / nullif(max(holder_count) FILTER (rn = 2), 0)) - 1 holder_change
          FROM (
            SELECT instrument_id, holder_count,
                   row_number() OVER (
                     PARTITION BY instrument_id
                     ORDER BY announced_on DESC, reporting_period DESC
                   ) rn
            FROM holder_source
            WHERE announced_on <= ?
              AND CAST(available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
          ) WHERE rn <= 2 GROUP BY instrument_id
        )
        SELECT l.instrument_id, l.instrument_name, l.industry_code, l.effective_from,
               b.r1, b.r5, b.r20, b.r60, b.position120, l.turnover_rate,
               l.amount_share, b.volatility20, b.downside20, b.dd60,
               l.price_earnings_ttm, l.price_book, l.dividend_yield_ttm,
               h.holder_change, coalesce(x.attention, 0), b.below_ma
        FROM latest l LEFT JOIN bar_features b USING (instrument_id)
        LEFT JOIN lhb x USING (instrument_id)
        LEFT JOIN holders h USING (instrument_id)
        ORDER BY l.instrument_id
        """,
        [
            paths["daily_tradability"],
            cutoff,
            paths["industry_membership"],
            cutoff,
            cutoff,
            cutoff,
            paths["adjusted_market"],
            cutoff,
            paths["daily_basic"],
            cutoff,
            paths["daily_market"],
            cutoff,
            cutoff,
            cutoff,
            cutoff,
            cutoff,
            cutoff,
        ],
    ).fetchall()
    return tuple(RankingFeature(*row) for row in rows)


def bounded_paths(
    paths: dict[str, list[str]],
    cutoff: date,
) -> dict[str, list[str]]:
    bounded = dict(paths)
    for name in (
        "adjusted_market",
        "daily_basic",
        "daily_market",
        "daily_tradability",
        "lhb_event",
        "shareholder_count",
    ):
        values = paths.get(name, [])
        recent = [
            item
            for item in values
            if _artifact_year(item) == 0 or _artifact_year(item) >= cutoff.year - 1
        ]
        bounded[name] = recent or values
    return bounded


def _optional_sources(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
) -> None:
    if paths.get("lhb_event"):
        connection.execute(
            "CREATE OR REPLACE TEMP VIEW lhb_source AS SELECT * FROM read_parquet("
            + _sql_paths(paths["lhb_event"])
            + ")"
        )
    else:
        connection.execute(
            "CREATE OR REPLACE TEMP TABLE lhb_source ("
            "instrument_id VARCHAR, trade_date DATE, available_at TIMESTAMPTZ)"
        )
    if paths.get("shareholder_count"):
        connection.execute(
            "CREATE OR REPLACE TEMP VIEW holder_source AS SELECT * FROM read_parquet("
            + _sql_paths(paths["shareholder_count"])
            + ")"
        )
    else:
        connection.execute(
            "CREATE OR REPLACE TEMP TABLE holder_source ("
            "instrument_id VARCHAR, announced_on DATE, reporting_period DATE,"
            "holder_count BIGINT, available_at TIMESTAMPTZ)"
        )


def _artifact_year(path: str) -> int:
    try:
        return int(Path(path).stem.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _sql_paths(paths: list[str]) -> str:
    return "[" + ",".join("'" + item.replace("'", "''") + "'" for item in paths) + "]"


__all__ = ["bounded_paths", "ranking_features"]
