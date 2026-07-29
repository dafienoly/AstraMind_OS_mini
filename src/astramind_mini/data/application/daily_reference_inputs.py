"""Daily full reconciliation of reference and point-in-time identity datasets."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb
from pydantic import BaseModel

from ..contracts import DatasetManifest, IndustryTaxonomyObservation, RawRecordEnvelope
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, ProviderTable, RawRecordStore
from .daily_reference_normalization import (
    DIVIDEND_FIELDS,
    NAME_CHANGE_FIELDS,
    normalize_corporate_actions,
    normalize_name_history,
)
from .dataset_schemas import (
    CORPORATE_ACTION_COLUMNS,
    INDUSTRY_MEMBERSHIP_COLUMNS,
    INDUSTRY_TAXONOMY_COLUMNS,
    SECURITY_MASTER_COLUMNS,
    SECURITY_NAME_HISTORY_COLUMNS,
)
from .datasets import build_dataset_manifest_from_hashes
from .historical_publication import FileArtifacts
from .identity import content_hash, file_hash
from .industry_foundation_support import (
    MEMBERSHIP_FIELDS,
    TAXONOMY_FIELDS,
    canonicalize_l2_parents,
    membership_overlap_stats,
)
from .industry_normalization import normalize_memberships, normalize_taxonomy
from .normalization import normalize_security_master
from .publication_policy import SECURITY_FIELDS
from .state_files import save_state, write_bytes_atomic


@dataclass(frozen=True, slots=True)
class DailyReferenceInputs:
    manifests: dict[str, DatasetManifest]
    artifacts: FileArtifacts
    paths: dict[str, Path]
    retrieved_at: datetime


async def prepare_daily_reference_inputs(
    *,
    root: Path,
    provider: HistoricalMarketDataProvider,
    raw_store: RawRecordStore,
    encoder: ParquetEncoder,
    manifests: dict[str, DatasetManifest],
    base_paths: dict[str, tuple[Path, ...]],
    workspace: Path,
    state: dict[str, object],
    state_path: Path,
    run_id: str,
    target_date: date,
) -> DailyReferenceInputs:
    required = {
        "security_master",
        "security_name_history",
        "corporate_action",
        "industry_taxonomy",
        "industry_membership",
    }
    if not required <= manifests.keys():
        missing = sorted(required - manifests.keys())
        raise ValueError(f"日度基准刷新缺少基础数据集：{','.join(missing)}")
    request_state = state.setdefault("references", {})
    if not isinstance(request_state, dict):
        raise ValueError("日度基准请求状态格式无效")
    collector = _Collector(
        provider, raw_store, encoder, workspace, state, state_path, request_state
    )

    security_path, security_times = await _collect_security(collector)
    taxonomy, taxonomy_path, taxonomy_times = await _collect_taxonomy(collector)
    membership_path, membership_times = await _collect_memberships(collector, taxonomy)
    name_path, name_times = await _collect_names(
        collector,
        security_path,
        base_paths["security_name_history"],
    )
    action_path, action_times = await _collect_actions(
        collector, base_paths["corporate_action"], target_date
    )
    paths = {
        "security_master": security_path,
        "security_name_history": name_path,
        "corporate_action": action_path,
        "industry_taxonomy": taxonomy_path,
        "industry_membership": membership_path,
    }
    retrieved_at = max(
        *security_times,
        *taxonomy_times,
        *membership_times,
        *name_times,
        *action_times,
    )
    request_identity = content_hash(
        {
            "run_id": run_id,
            "policy": "daily-reference-v1.3",
            "artifacts": {name: file_hash(path) for name, path in paths.items()},
        }
    )
    output_manifests, artifacts = {}, {}
    for name, path in paths.items():
        manifest = _manifest(
            base=manifests[name],
            name=name,
            path=path,
            request_identity=request_identity,
            retrieved_at=retrieved_at,
            target_date=target_date,
        )
        output_manifests[name] = manifest
        artifacts[name] = {f"{name}.parquet": (path, file_hash(path))}
    return DailyReferenceInputs(output_manifests, artifacts, paths, retrieved_at)


async def _collect_security(collector: _Collector) -> tuple[Path, tuple[datetime, ...]]:
    parts = tuple(
        [
            await collector.collect(
                api_name="stock_basic",
                key=status,
                params={"list_status": status},
                fields=SECURITY_FIELDS,
                columns=SECURITY_MASTER_COLUMNS,
                normalize=lambda table: normalize_security_master((table,)),
                limit=10_000,
            )
            for status in ("L", "D", "P")
        ]
    )
    path = collector.workspace / "references" / "security_master.parquet"
    _compact(tuple(item[0] for item in parts), path, ("instrument_id",))
    return path, tuple(item[1] for item in parts)


async def _collect_taxonomy(
    collector: _Collector,
) -> tuple[tuple[IndustryTaxonomyObservation, ...], Path, tuple[datetime, ...]]:
    tables, normalized = [], []
    for level in ("L1", "L2"):
        table = await collector.query(
            api_name="index_classify",
            key=level,
            params={"level": level, "src": "SW2021"},
            fields=TAXONOMY_FIELDS,
            limit=1_000,
        )
        rows = normalize_taxonomy(table, level=level)
        if level == "L1" and len(rows) != 31:
            raise ValueError(f"SW2021 一级行业数量异常：{len(rows)}，期望 31")
        tables.append(table)
        normalized.append(rows)
    taxonomy = (*normalized[0], *canonicalize_l2_parents(*normalized))
    path = collector.workspace / "references" / "industry_taxonomy.parquet"
    write_bytes_atomic(path, collector.encoder.encode(taxonomy, INDUSTRY_TAXONOMY_COLUMNS))
    return taxonomy, path, tuple(table.received_at for table in tables)


async def _collect_memberships(
    collector: _Collector,
    taxonomy: tuple[IndustryTaxonomyObservation, ...],
) -> tuple[Path, tuple[datetime, ...]]:
    parts = []
    for industry in taxonomy:
        for current in (True, False):
            status = "Y" if current else "N"
            parts.append(
                await collector.collect(
                    api_name="index_member_all",
                    key=f"{industry.level}-{industry.industry_code}-{status}",
                    params={
                        "l1_code" if industry.level == "L1" else "l2_code": industry.industry_code,
                        "is_new": status,
                    },
                    fields=MEMBERSHIP_FIELDS,
                    columns=INDUSTRY_MEMBERSHIP_COLUMNS,
                    normalize=_membership_normalizer(industry, current),
                    limit=2_000,
                )
            )
    path = collector.workspace / "references" / "industry_membership.parquet"
    _compact(
        tuple(item[0] for item in parts),
        path,
        ("industry_code", "instrument_id", "effective_from", "effective_to"),
    )
    membership_overlap_stats(path)
    return path, tuple(item[1] for item in parts)


async def _collect_names(
    collector: _Collector,
    security_path: Path,
    base_paths: tuple[Path, ...],
) -> tuple[Path, tuple[datetime, ...]]:
    parts = []
    for instrument_id in _changed_name_instruments(security_path, base_paths):
        parts.append(
            await collector.collect(
                api_name="namechange",
                key=instrument_id,
                params={"ts_code": instrument_id},
                fields=NAME_CHANGE_FIELDS,
                columns=SECURITY_NAME_HISTORY_COLUMNS,
                normalize=lambda table: normalize_name_history((table,)),
                limit=10_000,
            )
        )
    path = collector.workspace / "references" / "security_name_history.parquet"
    _compact(
        (*base_paths, *(item[0] for item in parts)),
        path,
        ("instrument_id", "effective_start_date", "name"),
    )
    _repair_name_intervals(path)
    return path, tuple(item[1] for item in parts)


def _changed_name_instruments(
    security_path: Path,
    name_paths: tuple[Path, ...],
) -> tuple[str, ...]:
    with duckdb.connect(":memory:") as connection:
        rows = connection.execute(
            """
            WITH latest AS (
              SELECT instrument_id, name
              FROM read_parquet(?)
              QUALIFY row_number() OVER (
                PARTITION BY instrument_id ORDER BY effective_start_date DESC, name
              ) = 1
            )
            SELECT security.instrument_id
            FROM read_parquet(?) security
            LEFT JOIN latest USING (instrument_id)
            WHERE latest.instrument_id IS NULL OR latest.name <> security.name
            ORDER BY security.instrument_id
            """,
            [[str(path) for path in name_paths], str(security_path)],
        ).fetchall()
    return tuple(str(row[0]) for row in rows)


async def _collect_actions(
    collector: _Collector,
    base_paths: tuple[Path, ...],
    target_date: date,
) -> tuple[Path, tuple[datetime, ...]]:
    parts = []
    for day_offset in range(8):
        key_date = target_date - timedelta(days=day_offset)
        for parameter in ("ann_date", "imp_ann_date"):
            parts.append(
                await collector.collect(
                    api_name="dividend",
                    key=f"{parameter}-{key_date:%Y%m%d}",
                    params={parameter: f"{key_date:%Y%m%d}"},
                    fields=DIVIDEND_FIELDS,
                    columns=CORPORATE_ACTION_COLUMNS,
                    normalize=lambda table: normalize_corporate_actions((table,)),
                    limit=10_000,
                )
            )
    path = collector.workspace / "references" / "corporate_action.parquet"
    _compact(
        (*base_paths, *(item[0] for item in parts)),
        path,
        ("provider_record_hash",),
    )
    return path, tuple(item[1] for item in parts)


class _Collector:
    def __init__(
        self,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
        workspace: Path,
        state: dict[str, object],
        state_path: Path,
        requests: dict[str, object],
    ) -> None:
        self.provider, self.raw, self.encoder = provider, raw_store, encoder
        self.workspace, self.state, self.state_path, self.requests = (
            workspace,
            state,
            state_path,
            requests,
        )

    async def query(
        self,
        *,
        api_name: str,
        key: str,
        params: dict[str, str],
        fields: tuple[str, ...],
        limit: int,
    ) -> ProviderTable:
        table = await self.provider.query(api_name, params=params, fields=fields)
        if len(table.rows) >= limit:
            raise ValueError(f"{api_name}:{key} 达到提供方上限，拒绝截断结果")
        _preserve_raw(table, self.raw)
        return table

    async def collect(
        self,
        *,
        api_name: str,
        key: str,
        params: dict[str, str],
        fields: tuple[str, ...],
        columns: tuple[tuple[str, str], ...],
        normalize: Callable[[ProviderTable], Sequence[BaseModel]],
        limit: int,
    ) -> tuple[Path, datetime]:
        identity = f"{api_name}:{key}"
        cached = self.requests.get(identity)
        if isinstance(cached, dict):
            path = Path(str(cached.get("path", "")))
            if path.is_file() and file_hash(path) == cached.get("hash"):
                return path, datetime.fromisoformat(str(cached["received_at"]))
        table = await self.query(
            api_name=api_name,
            key=key,
            params=params,
            fields=fields,
            limit=limit,
        )
        path = self.workspace / "references" / "requests" / api_name / f"{key}.parquet"
        write_bytes_atomic(path, self.encoder.encode(normalize(table), columns))
        self.requests[identity] = {
            "path": str(path),
            "hash": file_hash(path),
            "received_at": table.received_at.isoformat(),
            "request_identity": table.request_identity,
        }
        save_state(self.state_path, self.state)
        return path, table.received_at


def _compact(paths: Sequence[Path], output: Path, keys: tuple[str, ...]) -> None:
    if not paths:
        raise ValueError(f"{output.name} 没有可合并的输入")
    output.parent.mkdir(parents=True, exist_ok=True)
    order = ", ".join(keys)
    temporary = output.with_suffix(".parquet.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM read_parquet(?)
              QUALIFY row_number() OVER (
                PARTITION BY {order} ORDER BY retrieved_at DESC, source_record_hash DESC
              ) = 1
              ORDER BY {order}
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [[str(path) for path in paths]],
        )
    temporary.replace(output)


def _manifest(
    *,
    base: DatasetManifest,
    name: str,
    path: Path,
    request_identity: str,
    retrieved_at: datetime,
    target_date: date,
) -> DatasetManifest:
    with duckdb.connect(":memory:") as connection:
        row = connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)]).fetchone()
        assert row is not None
        row_count = int(row[0])
    gaps = tuple(
        gap
        for gap in base.known_gaps
        if not (
            gap.startswith("current_")
            or gap in {"security_name_history_not_available", "corporate_action_not_available"}
        )
    )
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.1.0",
        provider="tushare",
        source_endpoint={
            "security_master": "stock_basic",
            "security_name_history": "namechange",
            "corporate_action": "dividend",
            "industry_taxonomy": "index_classify",
            "industry_membership": "index_member_all",
        }[name],
        request_identity=request_identity,
        retrieved_at=retrieved_at,
        market_timezone=base.market_timezone,
        date_range=(min(base.date_range[0], target_date), max(base.date_range[1], target_date)),
        universe=base.universe,
        primary_key=base.primary_key,
        availability_rule=base.availability_rule,
        units=base.units,
        row_count=row_count,
        artifact_hashes={f"{name}.parquet": file_hash(path)},
        known_gaps=gaps,
        critical_gaps=base.critical_gaps,
    )


def _repair_name_intervals(path: Path) -> None:
    temporary = path.with_suffix(".parquet.intervals.tmp")
    temporary.unlink(missing_ok=True)
    target = str(temporary).replace("'", "''")
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              WITH ordered AS (
                SELECT *,
                       lead(effective_start_date) OVER (
                         PARTITION BY instrument_id
                         ORDER BY effective_start_date, name
                       ) AS next_start
                FROM read_parquet(?)
              )
              SELECT * EXCLUDE (next_start) REPLACE (
                CASE
                  WHEN next_start IS NULL THEN provider_end_date
                  WHEN provider_end_date IS NULL THEN next_start
                  ELSE least(provider_end_date, next_start)
                END AS effective_end_date
              )
              FROM ordered
              ORDER BY instrument_id, effective_start_date, name
            ) TO '{target}' (FORMAT PARQUET, COMPRESSION ZSTD)
            """,
            [str(path)],
        )
    temporary.replace(path)


def _preserve_raw(table: ProviderTable, raw_store: RawRecordStore) -> None:
    envelope = RawRecordEnvelope(
        provider="tushare",
        interface_name=table.api_name,
        source_endpoint=table.source_endpoint,
        request_identity=table.request_identity,
        received_at=table.received_at,
        schema_version="provider-v1",
        content_hash=content_hash(table.raw_body),
    )
    raw_store.append(envelope, table.raw_body)


def _membership_normalizer(
    industry: IndustryTaxonomyObservation,
    current: bool,
) -> Callable[[ProviderTable], Sequence[BaseModel]]:
    def normalize(table: ProviderTable) -> Sequence[BaseModel]:
        return normalize_memberships(
            table,
            industry_code=industry.industry_code,
            industry_name=industry.industry_name,
            is_current=current,
            level=industry.level,
        )

    return normalize


__all__ = ["DailyReferenceInputs", "prepare_daily_reference_inputs"]
