"""Synthetic immutable DataSnapshot fixture for WP-0062 production tests."""

from __future__ import annotations

import calendar
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from astramind_mini.data.adapters import (
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application import (
    DataSnapshotBuilder,
    build_dataset_manifest,
    content_hash,
)
from astramind_mini.data.contracts import DatasetManifest

SHANGHAI = ZoneInfo("Asia/Shanghai")
PARAMETERS = (
    {
        "learning_rate": 0.05,
        "max_leaf_nodes": 7,
        "min_samples_leaf": 2,
        "l2_regularization": 1.0,
        "max_iter": 20,
        "max_features": 1.0,
        "random_state": 20260729,
    },
)
INDUSTRIES = (
    ("801010.SI", "行业甲", "000001.SZ"),
    ("801020.SI", "行业乙", "000002.SZ"),
    ("801030.SI", "行业丙", "000003.SZ"),
)


@dataclass(frozen=True)
class DatasetInput:
    name: str
    columns: tuple[tuple[str, str], ...]
    rows: tuple[tuple[object, ...], ...]
    primary_key: tuple[str, ...]
    known_gaps: tuple[str, ...] = ()


def production_snapshot(
    root: Path,
    *,
    include_official: bool = True,
    late_latest_industry: bool = False,
) -> tuple[Path, str, dict[str, DatasetManifest]]:
    data_root = root / "data"
    staging = root / "staging"
    days = _month_ends(date(2000, 1, 31), date(2023, 12, 31))
    cutoff = datetime.combine(days[-1], time(23), tzinfo=SHANGHAI)
    inputs = _dataset_inputs(
        days,
        cutoff=cutoff,
        late_latest_industry=late_latest_industry,
    )
    manifests = {
        item.name: _publish_dataset(
            item,
            data_root=data_root,
            staging=staging,
            days=days,
            cutoff=cutoff,
        )
        for item in inputs
        if include_official or item.name != "official_index_daily"
    }
    snapshot = DataSnapshotBuilder().build(
        manifests=tuple(manifests.values()),
        as_of=cutoff,
        created_at=cutoff,
        code_identity="test:wp-0062-data",
    )
    FilesystemSnapshotStore(data_root).publish(snapshot)
    return data_root, snapshot.snapshot_id, manifests


def _dataset_inputs(
    days: tuple[date, ...],
    *,
    cutoff: datetime,
    late_latest_industry: bool,
) -> tuple[DatasetInput, ...]:
    available = tuple(datetime.combine(day, time(18), tzinfo=SHANGHAI) for day in days)
    market, industry = _market_inputs(
        days,
        available=available,
        late_latest_industry=late_latest_industry,
    )
    return (
        market,
        industry,
        _membership_input(cutoff),
        _benchmark_input(days, available),
    )


def _market_inputs(
    days: tuple[date, ...],
    *,
    available: tuple[datetime, ...],
    late_latest_industry: bool,
) -> tuple[DatasetInput, DatasetInput]:
    industry_rows: list[tuple[object, ...]] = []
    market_rows: list[tuple[object, ...]] = []
    closes: dict[str, list[float]] = {code: [] for code, _, _ in INDUSTRIES}
    for index, day in enumerate(days):
        for position, (code, name, instrument) in enumerate(INDUSTRIES):
            close = _industry_close(position, index)
            prior = closes[code][-1] if closes[code] else close
            closes[code].append(close)
            observed_at = available[index]
            if late_latest_industry and index == len(days) - 1 and position == 0:
                observed_at = datetime.combine(day, time(20), tzinfo=SHANGHAI)
            industry_rows.append(
                _industry_row(
                    code,
                    name,
                    day,
                    close,
                    position,
                    index,
                    observed_at,
                )
            )
            market_rows.append((instrument, day, (close / prior - 1.0) * 100.0, available[index]))
    return (
        DatasetInput(
            name="daily_market",
            columns=(
                ("instrument_id", "VARCHAR"),
                ("trade_date", "DATE"),
                ("percent_change", "DOUBLE"),
                ("available_at", "TIMESTAMPTZ"),
            ),
            rows=tuple(market_rows),
            primary_key=("instrument_id", "trade_date"),
        ),
        DatasetInput(
            name="industry_index_daily",
            columns=(
                ("taxonomy", "VARCHAR"),
                ("taxonomy_version", "VARCHAR"),
                ("level", "VARCHAR"),
                ("industry_code", "VARCHAR"),
                ("industry_name", "VARCHAR"),
                ("trade_date", "DATE"),
                ("close", "DOUBLE"),
                ("amount_provider_native", "DOUBLE"),
                ("price_earnings", "DOUBLE"),
                ("price_book", "DOUBLE"),
                ("available_at", "TIMESTAMPTZ"),
            ),
            rows=tuple(industry_rows),
            primary_key=("industry_code", "trade_date"),
        ),
    )


def _industry_row(
    code: str,
    name: str,
    day: date,
    close: float,
    position: int,
    index: int,
    observed_at: datetime,
) -> tuple[object, ...]:
    return (
        "SW",
        "SW2021",
        "L1",
        code,
        name,
        day,
        close,
        100_000_000.0 * (1.0 + position + (index % 7) / 10.0),
        10.0 + position + (index % 12) / 10.0,
        1.0 + position / 5.0,
        observed_at,
    )


def _membership_input(cutoff: datetime) -> DatasetInput:
    return DatasetInput(
        name="industry_membership",
        columns=(
            ("taxonomy", "VARCHAR"),
            ("taxonomy_version", "VARCHAR"),
            ("level", "VARCHAR"),
            ("industry_code", "VARCHAR"),
            ("instrument_id", "VARCHAR"),
            ("effective_from", "DATE"),
            ("effective_to", "DATE"),
            ("available_at", "TIMESTAMPTZ"),
            ("retrieved_at", "TIMESTAMPTZ"),
        ),
        rows=tuple(
            (
                "SW",
                "SW2021",
                "L1",
                code,
                instrument,
                date(2012, 1, 1),
                None,
                datetime(2012, 1, 1, 18, tzinfo=SHANGHAI),
                cutoff,
            )
            for code, _, instrument in INDUSTRIES
        ),
        primary_key=("industry_code", "instrument_id", "effective_from"),
        known_gaps=("historical_membership_publication_time_unavailable",),
    )


def _benchmark_input(
    days: tuple[date, ...],
    available: tuple[datetime, ...],
) -> DatasetInput:
    return DatasetInput(
        name="official_index_daily",
        columns=(
            ("index_code", "VARCHAR"),
            ("trade_date", "DATE"),
            ("close", "DOUBLE"),
            ("available_at", "TIMESTAMPTZ"),
        ),
        rows=tuple(
            (
                "000985.CSI",
                day,
                100.0 + index * 0.18 + math.sin(index / 6.0),
                available[index],
            )
            for index, day in enumerate(days)
        ),
        primary_key=("index_code", "trade_date"),
    )


def _publish_dataset(
    item: DatasetInput,
    *,
    data_root: Path,
    staging: Path,
    days: tuple[date, ...],
    cutoff: datetime,
) -> DatasetManifest:
    artifacts = {
        "data.parquet": _parquet_bytes(
            staging / f"{item.name}.parquet",
            item.columns,
            item.rows,
        )
    }
    manifest = build_dataset_manifest(
        dataset_name=item.name,
        schema_version="1.0.0",
        provider="synthetic",
        source_endpoint="fixture",
        request_identity=content_hash({"fixture": item.name}),
        retrieved_at=cutoff,
        market_timezone="Asia/Shanghai",
        date_range=(days[0], days[-1]),
        universe=tuple(value[0] for value in INDUSTRIES),
        primary_key=item.primary_key,
        availability_rule="fixture available_at",
        units=("fixture:unit",),
        row_count=len(item.rows),
        artifacts=artifacts,
        known_gaps=item.known_gaps,
    )
    FilesystemDatasetStore(data_root).publish(manifest, artifacts)
    return manifest


def _parquet_bytes(
    path: Path,
    columns: Sequence[tuple[str, str]],
    rows: Sequence[tuple[object, ...]],
) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    definitions = ", ".join(f'"{name}" {kind}' for name, kind in columns)
    placeholders = ", ".join("?" for _ in columns)
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"CREATE TABLE dataset ({definitions})")
        connection.executemany(f"INSERT INTO dataset VALUES ({placeholders})", rows)
        connection.execute(
            "COPY dataset TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
            [str(path)],
        )
    return path.read_bytes()


def _month_ends(start: date, end: date) -> tuple[date, ...]:
    result = []
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        result.append(date(year, month, calendar.monthrange(year, month)[1]))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(result)


def _industry_close(position: int, index: int) -> float:
    if position == 0:
        return 100.0 + index * 0.32 + 0.012 * index**2
    if position == 1:
        return 105.0 + index * 0.25 + 3.0 * math.sin(index / 4.0)
    return 110.0 + index * 0.14 + 4.0 * math.cos(index / 7.0)


__all__ = ["INDUSTRIES", "PARAMETERS", "SHANGHAI", "production_snapshot"]
