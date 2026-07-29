"""Validate and describe the approved date-bound market-provider cutover."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from ..contracts import DatasetProviderEpoch

MINIQMT_CUTOVER_DATE = date(2026, 7, 29)
LEGACY_PROVIDER = "tushare"
CURRENT_PROVIDER = "miniqmt"
NON_PRODUCTION_PROVIDERS = frozenset({"synthetic", "fixture"})


@dataclass(frozen=True, slots=True)
class SourceAttribution:
    provider: str
    source_endpoint: str
    provider_lineage: tuple[DatasetProviderEpoch, ...] = ()


def market_source_attribution(
    paths: tuple[Path, ...],
    *,
    date_column: str = "trade_date",
) -> SourceAttribution:
    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            f"""
            SELECT provider, source_endpoint, min({date_column}), max({date_column})
            FROM read_parquet(?)
            GROUP BY provider, source_endpoint
            ORDER BY provider, source_endpoint
            """,
            [[str(path) for path in paths]],
        ).fetchall()
        providers = {str(row[0]) for row in rows}
        production = providers - NON_PRODUCTION_PROVIDERS
        if len(production) == 1:
            provider = next(iter(production))
            endpoints = {str(row[1]) for row in rows if str(row[0]) == provider}
            return SourceAttribution(provider, _endpoint(endpoints))
        if providers == {LEGACY_PROVIDER, CURRENT_PROVIDER}:
            validation = connection.execute(
                f"""
                SELECT
                    count(*) FILTER (
                        WHERE ({date_column} < ? AND provider <> ?)
                           OR ({date_column} >= ? AND provider <> ?)
                    ),
                    (
                        SELECT count(*) FROM (
                            SELECT {date_column}
                            FROM read_parquet(?)
                            GROUP BY {date_column}
                            HAVING count(DISTINCT provider) > 1
                        )
                    )
                FROM read_parquet(?)
                """,
                [
                    MINIQMT_CUTOVER_DATE,
                    LEGACY_PROVIDER,
                    MINIQMT_CUTOVER_DATE,
                    CURRENT_PROVIDER,
                    [str(path) for path in paths],
                    [str(path) for path in paths],
                ],
            ).fetchone()
            assert validation is not None
            invalid, mixed_dates = validation
            if invalid or mixed_dates:
                raise ValueError(
                    "行情提供方日期切换边界无效："
                    f"boundary_violations={invalid},mixed_dates={mixed_dates}"
                )
            endpoint_by_provider = {
                provider: _endpoint({str(row[1]) for row in rows if str(row[0]) == provider})
                for provider in (LEGACY_PROVIDER, CURRENT_PROVIDER)
            }
            return SourceAttribution(
                provider="date-bound-cutover",
                source_endpoint="multiple-provider-endpoints",
                provider_lineage=(
                    DatasetProviderEpoch(
                        provider=LEGACY_PROVIDER,
                        source_endpoint=endpoint_by_provider[LEGACY_PROVIDER],
                        effective_from=min(
                            row[2] for row in rows if str(row[0]) == LEGACY_PROVIDER
                        ),
                        effective_to=MINIQMT_CUTOVER_DATE.fromordinal(
                            MINIQMT_CUTOVER_DATE.toordinal() - 1
                        ),
                    ),
                    DatasetProviderEpoch(
                        provider=CURRENT_PROVIDER,
                        source_endpoint=endpoint_by_provider[CURRENT_PROVIDER],
                        effective_from=MINIQMT_CUTOVER_DATE,
                    ),
                ),
            )
    raise ValueError("行情数据集包含未批准的提供方组合：" + ",".join(sorted(providers)))


def market_artifact_matches_epoch(
    path: Path,
    target_date: date,
    *,
    date_column: str = "trade_date",
) -> bool:
    expected = LEGACY_PROVIDER if target_date < MINIQMT_CUTOVER_DATE else CURRENT_PROVIDER
    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            f"""
            SELECT DISTINCT provider
            FROM read_parquet(?)
            WHERE {date_column} = ?
            """,
            [str(path), target_date],
        ).fetchall()
    providers = {str(row[0]) for row in rows}
    return bool(providers) and (providers <= NON_PRODUCTION_PROVIDERS or providers == {expected})


def _endpoint(values: set[str]) -> str:
    return next(iter(values)) if len(values) == 1 else "multiple-provider-endpoints"


__all__ = [
    "CURRENT_PROVIDER",
    "LEGACY_PROVIDER",
    "MINIQMT_CUTOVER_DATE",
    "SourceAttribution",
    "market_artifact_matches_epoch",
    "market_source_attribution",
]
