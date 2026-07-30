"""Load point-in-time historical inputs from verified immutable Parquet artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import duckdb

from .snapshot import ProductionInputError, VerifiedSnapshot

BENCHMARK_ID = "000985.CSI"
REQUIRED_DATASETS = (
    "daily_market",
    "industry_index_daily",
    "industry_membership",
    "official_index_daily",
)


@dataclass(frozen=True)
class IndustryBar:
    industry_code: str
    trade_date: date
    close: float
    amount: float | None
    price_earnings: float | None
    price_book: float | None


@dataclass(frozen=True)
class BreadthObservation:
    industry_code: str
    trade_date: date
    member_count: int
    covered_count: int
    advancing_count: int
    declining_count: int


@dataclass(frozen=True)
class ProductionHistory:
    industry_bars: tuple[IndustryBar, ...]
    benchmark_closes: dict[date, float]
    breadth: dict[tuple[str, date], BreadthObservation]
    membership_reconstructed: bool


class ProductionHistoryReader:
    def load(self, verified: VerifiedSnapshot) -> ProductionHistory:
        paths = verified.parquet_paths
        with duckdb.connect(":memory:") as connection:
            bars = self._industry_bars(
                connection,
                paths["industry_index_daily"],
                verified.snapshot.as_of,
            )
            benchmark = self._benchmark(
                connection,
                paths["official_index_daily"],
                verified.snapshot.as_of,
            )
            breadth = self._breadth(
                connection,
                industry_paths=paths["industry_index_daily"],
                membership_paths=paths["industry_membership"],
                market_paths=paths["daily_market"],
                cutoff=verified.snapshot.as_of,
            )
        if len({item.industry_code for item in bars}) < 3:
            raise ProductionInputError("industry_cross_section_below_three")
        membership = verified.manifests["industry_membership"]
        reconstructed = any(
            reason
            in {
                "historical_membership_publication_time_unavailable",
                "reconstructed_not_then_known",
            }
            for reason in membership.known_gaps
        )
        return ProductionHistory(
            industry_bars=bars,
            benchmark_closes=benchmark,
            breadth=breadth,
            membership_reconstructed=reconstructed,
        )

    def _industry_bars(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
        cutoff: datetime,
    ) -> tuple[IndustryBar, ...]:
        rows = connection.execute(
            """
            SELECT industry_code, trade_date, close, amount_provider_native,
                   price_earnings, price_book
            FROM read_parquet(?, union_by_name=true)
            WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021' AND level = 'L1'
              AND available_at <= ?
              AND available_at <= (
                CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
              ) AT TIME ZONE 'Asia/Shanghai'
            ORDER BY industry_code, trade_date
            """,
            [[str(path) for path in paths], cutoff],
        ).fetchall()
        result = tuple(
            IndustryBar(
                industry_code=str(code),
                trade_date=day,
                close=float(close),
                amount=_optional_float(amount),
                price_earnings=_optional_float(pe),
                price_book=_optional_float(pb),
            )
            for code, day, close, amount, pe, pb in rows
            if close is not None and float(close) > 0
        )
        if not result:
            raise ProductionInputError("industry_index_history_empty")
        return result

    def _benchmark(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
        cutoff: datetime,
    ) -> dict[date, float]:
        rows = connection.execute(
            """
            SELECT trade_date, close
            FROM read_parquet(?, union_by_name=true)
            WHERE index_code = ? AND available_at <= ?
              AND available_at <= (
                CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
              ) AT TIME ZONE 'Asia/Shanghai'
            ORDER BY trade_date
            """,
            [[str(path) for path in paths], BENCHMARK_ID, cutoff],
        ).fetchall()
        result = {day: float(close) for day, close in rows if close is not None and close > 0}
        if not result:
            raise ProductionInputError("official_benchmark_history_empty")
        return result

    def _breadth(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        industry_paths: tuple[Path, ...],
        membership_paths: tuple[Path, ...],
        market_paths: tuple[Path, ...],
        cutoff: datetime,
    ) -> dict[tuple[str, date], BreadthObservation]:
        rows = connection.execute(
            """
            WITH dates AS (
              SELECT DISTINCT trade_date
              FROM read_parquet(?, union_by_name=true)
              WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021' AND level = 'L1'
                AND available_at <= ?
                AND available_at <= (
                  CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
                ) AT TIME ZONE 'Asia/Shanghai'
            ), memberships AS (
              SELECT industry_code, instrument_id, effective_from, effective_to, available_at
              FROM read_parquet(?, union_by_name=true)
              WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021' AND level = 'L1'
              QUALIFY row_number() OVER (
                PARTITION BY industry_code, instrument_id, effective_from, effective_to
                ORDER BY retrieved_at DESC
              ) = 1
            ), active AS (
              SELECT d.trade_date, m.industry_code, m.instrument_id
              FROM dates d JOIN memberships m
               ON m.effective_from <= d.trade_date
               AND (m.effective_to IS NULL OR d.trade_date < m.effective_to)
               AND m.available_at <= (
                 CAST(d.trade_date AS TIMESTAMP) + INTERVAL '18 hours'
               ) AT TIME ZONE 'Asia/Shanghai'
            ), market AS (
              SELECT instrument_id, trade_date, percent_change, available_at
              FROM read_parquet(?, union_by_name=true)
              WHERE available_at <= ?
            )
            SELECT a.industry_code, a.trade_date,
                   count(*) AS member_count,
                   count(m.percent_change) AS covered_count,
                   count(*) FILTER (WHERE m.percent_change > 0) AS advancing_count,
                   count(*) FILTER (WHERE m.percent_change < 0) AS declining_count
            FROM active a LEFT JOIN market m
              ON m.instrument_id = a.instrument_id AND m.trade_date = a.trade_date
             AND m.available_at <= (
               CAST(a.trade_date AS TIMESTAMP) + INTERVAL '18 hours'
             ) AT TIME ZONE 'Asia/Shanghai'
            GROUP BY a.industry_code, a.trade_date
            ORDER BY a.industry_code, a.trade_date
            """,
            [
                [str(path) for path in industry_paths],
                cutoff,
                [str(path) for path in membership_paths],
                [str(path) for path in market_paths],
                cutoff,
            ],
        ).fetchall()
        return {
            (str(code), day): BreadthObservation(
                industry_code=str(code),
                trade_date=day,
                member_count=int(member_count),
                covered_count=int(covered),
                advancing_count=int(advancing),
                declining_count=int(declining),
            )
            for code, day, member_count, covered, advancing, declining in rows
        }


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


__all__ = [
    "BENCHMARK_ID",
    "REQUIRED_DATASETS",
    "BreadthObservation",
    "IndustryBar",
    "ProductionHistory",
    "ProductionHistoryReader",
]
