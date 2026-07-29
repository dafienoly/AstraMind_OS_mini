"""Daily stock inputs and derived research projections for WP-0029 freshness."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import cast

import duckdb

from ..adapters import (
    DuckDBCorporateActionProjector,
    DuckDBHistoricalStatusProjector,
)
from ..contracts import DatasetManifest
from ..ports import (
    HistoricalMarketDataProvider,
    ParquetEncoder,
    RawRecordStore,
)
from .constraint_supplements import ConstraintSupplementService
from .datasets import build_dataset_manifest_from_hashes
from .historical_supplements import HistoricalSupplementService
from .identity import file_hash
from .state_files import load_state

SOURCE_DATASETS = (
    "daily_market",
    "adjustment_factor",
    "daily_basic",
    "price_limit",
    "suspension_event",
)


async def publish_daily_research_inputs(
    *,
    root: Path,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    manifests: dict[str, DatasetManifest],
    paths: dict[str, tuple[Path, ...]],
    workspace: Path,
    calendar_path: Path,
    run_id: str,
    target_date: date,
    retrieved_at: datetime,
    reference_paths: dict[str, Path] | None = None,
) -> tuple[dict[str, DatasetManifest], dict[str, Path], datetime]:
    market_state_path = workspace / "research" / "market-state.json"
    constraint_state_path = workspace / "research" / "constraint-state.json"
    market_state = load_state(market_state_path) or {"supplements": {}}
    constraints_state = load_state(constraint_state_path) or {"supplements": {}}
    await HistoricalSupplementService(
        provider=provider,
        raw_store=raw_store,
        encoder=encoder,
    ).prepare(
        staging=workspace / "research",
        state=market_state,
        state_path=market_state_path,
        missing_daily=frozenset({target_date}),
        missing_factors=frozenset({target_date}),
    )
    await ConstraintSupplementService(
        provider=provider,
        raw_store=raw_store,
        encoder=encoder,
    ).prepare(
        staging=workspace / "research",
        state=constraints_state,
        state_path=constraint_state_path,
        missing={
            "daily_basic": frozenset({target_date}),
            "stk_limit": frozenset({target_date}),
            "suspend_d": frozenset({target_date}),
        },
    )
    replacements = _source_replacements(
        root=root,
        manifests=manifests,
        paths=paths,
        workspace=workspace,
        market_state=market_state,
        constraints_state=constraints_state,
        target_date=target_date,
    )
    retrieved_at = max(
        retrieved_at,
        *_supplement_received_times(market_state, constraints_state, target_date),
    )
    staged_manifests = {
        name: _reversion_manifest(
            root=root,
            base=manifests[name],
            replacement=replacements[name],
            target_date=target_date,
            retrieved_at=retrieved_at,
            run_id=run_id,
        )
        for name in SOURCE_DATASETS
    }
    derived = _derive_research_inputs(
        paths=paths,
        manifests=manifests,
        source_replacements=replacements,
        workspace=workspace,
        target_date=target_date,
        retrieved_at=retrieved_at,
        calendar_path=calendar_path,
        reference_paths=reference_paths or {},
    )
    for name in ("adjusted_market", "daily_tradability"):
        staged_manifests[name] = _reversion_manifest(
            root=root,
            base=manifests[name],
            replacement=derived[name],
            target_date=target_date,
            retrieved_at=retrieved_at,
            run_id=run_id,
        )
    return staged_manifests, {**replacements, **derived}, retrieved_at


def artifact_sources(
    root: Path,
    base: DatasetManifest,
    published: DatasetManifest,
    replacement: Path,
) -> dict[str, tuple[Path, str]]:
    digest = base.dataset_version.rsplit(":", 1)[-1]
    directory = root / "datasets" / base.dataset_name / digest
    year_name = replacement.name
    result = {}
    for name in published.artifact_paths:
        path = replacement if name == year_name else directory / name
        result[name] = (path, file_hash(path))
    return result


def _source_replacements(
    *,
    root: Path,
    manifests: dict[str, DatasetManifest],
    paths: dict[str, tuple[Path, ...]],
    workspace: Path,
    market_state: dict[str, object],
    constraints_state: dict[str, object],
    target_date: date,
) -> dict[str, Path]:
    market = cast(dict[str, object], market_state["supplements"])
    day = cast(dict[str, object], market[target_date.isoformat()])
    constraints = cast(dict[str, object], constraints_state["supplements"])
    inputs = {
        "daily_market": Path(str(day["daily"])),
        "adjustment_factor": Path(str(day["adj_factor"])),
        "daily_basic": _constraint_path(constraints, "daily_basic", target_date),
        "price_limit": _constraint_path(constraints, "stk_limit", target_date),
        "suspension_event": _constraint_path(constraints, "suspend_d", target_date),
    }
    result = {}
    for name, increment in inputs.items():
        base = _year_path(paths[name], target_date.year)
        output_name = _year_artifact_name(manifests[name], target_date.year)
        output = workspace / "research" / "merged" / output_name
        _merge_day(
            base=base,
            increment=increment,
            output=output,
            target_date=target_date,
            date_column="trade_date",
            order_by=("trade_date", "instrument_id"),
            identity_columns=manifests[name].primary_key,
        )
        result[name] = output
    return result


def _derive_research_inputs(
    *,
    paths: dict[str, tuple[Path, ...]],
    manifests: dict[str, DatasetManifest],
    source_replacements: dict[str, Path],
    workspace: Path,
    target_date: date,
    retrieved_at: datetime,
    calendar_path: Path,
    reference_paths: dict[str, Path],
) -> dict[str, Path]:
    derived_root = workspace / "research" / "derived"
    corporate = DuckDBCorporateActionProjector()
    factor_paths = _replace_year(
        paths["adjustment_factor"], source_replacements["adjustment_factor"], target_date.year
    )
    factor_anchors = derived_root / "factor-anchors.parquet"
    corporate.build_factor_anchors(factor_files=factor_paths, output=factor_anchors)
    prior = derived_root / "prior-index-anchors.parquet"
    _build_prior_index_anchors(_year_path(paths["adjusted_market"], target_date.year - 1), prior)
    adjusted = derived_root / _year_artifact_name(manifests["adjusted_market"], target_date.year)
    corporate.project_year(
        daily_files=(source_replacements["daily_market"],),
        factor_files=(source_replacements["adjustment_factor"],),
        action_history=reference_paths.get(
            "corporate_action", _only_parquet(paths["corporate_action"])
        ),
        factor_anchors=factor_anchors,
        previous_index_anchors=prior,
        output=adjusted,
        next_index_anchors=derived_root / "next-index-anchors.parquet",
        imported_at=retrieved_at,
    )
    tradability = derived_root / _year_artifact_name(
        manifests["daily_tradability"], target_date.year
    )
    DuckDBHistoricalStatusProjector().project_year(
        year=target_date.year,
        security_master=reference_paths.get(
            "security_master", _only_parquet(paths["security_master"])
        ),
        trade_calendar=calendar_path,
        daily_files=(source_replacements["daily_market"],),
        price_limit_files=(source_replacements["price_limit"],),
        suspension_files=(source_replacements["suspension_event"],),
        name_history=reference_paths.get(
            "security_name_history", _only_parquet(paths["security_name_history"])
        ),
        output=tradability,
        imported_at=retrieved_at,
    )
    return {"adjusted_market": adjusted, "daily_tradability": tradability}


def _reversion_manifest(
    *,
    root: Path,
    base: DatasetManifest,
    replacement: Path,
    target_date: date,
    retrieved_at: datetime,
    run_id: str,
) -> DatasetManifest:
    digest = base.dataset_version.rsplit(":", 1)[-1]
    directory = root / "datasets" / base.dataset_name / digest
    hashes = {
        name: file_hash(replacement if name == replacement.name else directory / name)
        for name in base.artifact_paths
    }
    parquet = [
        replacement if name == replacement.name else directory / name
        for name in base.artifact_paths
        if name.endswith(".parquet")
    ]
    with duckdb.connect(":memory:") as connection:
        row = connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [[str(path) for path in parquet]],
        ).fetchone()
        assert row is not None
        row_count = int(row[0])
    return build_dataset_manifest_from_hashes(
        dataset_name=base.dataset_name,
        schema_version=base.schema_version,
        provider=base.provider,
        source_endpoint=base.source_endpoint,
        request_identity="sha256:" + run_id.rsplit(":", 1)[-1],
        retrieved_at=retrieved_at,
        market_timezone=base.market_timezone,
        date_range=(base.date_range[0], target_date),
        universe=base.universe,
        primary_key=base.primary_key,
        availability_rule=base.availability_rule,
        units=base.units,
        row_count=row_count,
        artifact_hashes=hashes,
        known_gaps=base.known_gaps,
        critical_gaps=base.critical_gaps,
    )


def _merge_day(
    *,
    base: Path,
    increment: Path,
    output: Path,
    target_date: date,
    date_column: str,
    order_by: tuple[str, ...],
    identity_columns: tuple[str, ...],
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    ordering = ", ".join(order_by)
    identity = ", ".join(identity_columns)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?) WHERE {date_column} <> ?
              UNION ALL SELECT * FROM read_parquet(?)
              ORDER BY {ordering}
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [str(base), target_date, str(increment)],
        )
        row = connection.execute(
            f"""
            SELECT count(*) - count(DISTINCT ({identity}))
            FROM read_parquet(?)
            """,
            [str(temporary)],
        ).fetchone()
        assert row is not None
        duplicate = int(row[0])
    if duplicate:
        temporary.unlink(missing_ok=True)
        raise ValueError(f"日度增量合并后存在 {duplicate} 个重复身份")
    temporary.replace(output)


def _build_prior_index_anchors(source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    target = str(output).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT instrument_id, research_close_index,
                     raw_close AS last_raw_close,
                     adjustment_factor AS last_adjustment_factor,
                     trade_date AS last_trade_date
              FROM read_parquet(?)
              QUALIFY row_number() OVER (
                PARTITION BY instrument_id ORDER BY trade_date DESC
              ) = 1
              ORDER BY instrument_id
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [str(source)],
        )


def _constraint_path(constraints: dict[str, object], table: str, target_date: date) -> Path:
    values = cast(dict[str, object], constraints[table])
    value = cast(dict[str, object], values[target_date.isoformat()])
    return Path(str(value["path"]))


def _supplement_received_times(
    market_state: dict[str, object],
    constraints_state: dict[str, object],
    target_date: date,
) -> tuple[datetime, ...]:
    market = cast(dict[str, object], market_state["supplements"])
    day = cast(dict[str, object], market[target_date.isoformat()])
    constraints = cast(dict[str, object], constraints_state["supplements"])
    values = [
        datetime.fromisoformat(str(day["daily_received_at"])),
        datetime.fromisoformat(str(day["factor_received_at"])),
    ]
    for table in ("daily_basic", "stk_limit", "suspend_d"):
        rows = cast(dict[str, object], constraints[table])
        entry = cast(dict[str, object], rows[target_date.isoformat()])
        values.append(datetime.fromisoformat(str(entry["received_at"])))
    return tuple(values)


def _year_path(paths: tuple[Path, ...], year: int) -> Path:
    matches = tuple(path for path in paths if f"-{year}.parquet" in path.name)
    if len(matches) != 1:
        raise ValueError(f"无法唯一定位 {year} 年分区")
    return matches[0]


def _year_artifact_name(manifest: DatasetManifest, year: int) -> str:
    matches = tuple(name for name in manifest.artifact_paths if f"-{year}.parquet" in name)
    if len(matches) != 1:
        raise ValueError(f"无法唯一定位 {manifest.dataset_name} 的 {year} 年制品")
    return matches[0]


def _replace_year(paths: tuple[Path, ...], replacement: Path, year: int) -> tuple[Path, ...]:
    return tuple(
        replacement if path.name == replacement.name else path
        for path in paths
        if path.suffix == ".parquet"
    )


def _only_parquet(paths: tuple[Path, ...]) -> Path:
    matches = tuple(path for path in paths if path.suffix == ".parquet")
    if len(matches) != 1:
        raise ValueError("要求唯一 Parquet 制品")
    return matches[0]


__all__ = ["SOURCE_DATASETS", "artifact_sources", "publish_daily_research_inputs"]
