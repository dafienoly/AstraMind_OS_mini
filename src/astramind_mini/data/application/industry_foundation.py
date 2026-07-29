"""Resumable SW2021 L1/L2 industry foundation publication for REQ-2026-0008."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import Literal

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest, RawRecordEnvelope
from ..ports import (
    DataArtifactLedger,
    EventDatasetCompactor,
    FileDatasetStore,
    HistoricalMarketDataProvider,
    ParquetEncoder,
    ProviderTable,
    RawRecordStore,
    ReleasableSnapshotStore,
)
from .dataset_schemas import (
    INDUSTRY_INDEX_DAILY_COLUMNS,
    INDUSTRY_MEMBERSHIP_COLUMNS,
    INDUSTRY_TAXONOMY_COLUMNS,
)
from .identity import content_hash, file_hash
from .industry_foundation_support import (
    INDEX_DAILY_FIELDS,
    MEMBERSHIP_FIELDS,
    TAXONOMY_FIELDS,
    IndustryArtifacts,
    canonicalize_l2_parents,
    five_year_windows,
    membership_overlap_stats,
)
from .industry_normalization import (
    normalize_index_daily,
    normalize_memberships,
    normalize_taxonomy,
)
from .industry_publication import (
    IndustryFoundationPublication,
    publish_industry_foundation,
)
from .state_files import load_state, save_state, write_bytes_atomic


class IndustryFoundationService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
        compactor: EventDatasetCompactor,
        dataset_store: FileDatasetStore,
        snapshot_store: ReleasableSnapshotStore,
        ledger: DataArtifactLedger,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._raw_store = raw_store
        self._encoder = encoder
        self._compactor = compactor
        self._dataset_store = dataset_store
        self._snapshot_store = snapshot_store
        self._ledger = ledger

    async def run(
        self,
        *,
        base_snapshot_id: str,
        start_date: date,
        end_date: date,
        republish: bool = False,
        include_l2: bool = False,
    ) -> IndustryFoundationPublication:
        if start_date > end_date:
            raise ValueError("行业数据开始日期不能晚于结束日期")
        base = self._manifests(self._snapshot_store.get(base_snapshot_id))
        import_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "start_date": start_date,
                "end_date": end_date,
                "taxonomy": "SW2021:L1+L2" if include_l2 else "SW2021:L1",
                "policy": "wp-0026-industry-hierarchy-v1"
                if include_l2
                else "req-0008-industry-foundation-v1",
            }
        )
        staging = self._root / "imports" / import_id.rsplit(":", 1)[-1]
        state_path = staging / "state.json"
        state = load_state(state_path) or {
            "import_id": import_id,
            "started_at": datetime.now(UTC).isoformat(),
            "requests": {},
        }
        if (snapshot_id := state.get("snapshot_id")) and not republish:
            return self._completed(str(snapshot_id), state)
        artifacts = await self._collect_and_compact(
            start_date, end_date, staging, state, state_path, include_l2
        )
        return publish_industry_foundation(
            data_root=self._root,
            base=base,
            import_id=import_id,
            end_date=end_date,
            taxonomy_path=artifacts.taxonomy_path,
            membership_path=artifacts.membership_path,
            daily_path=artifacts.daily_path,
            taxonomy_rows=artifacts.taxonomy_rows,
            membership_stats=artifacts.membership_stats,
            daily_stats=artifacts.daily_stats,
            state=state,
            state_path=state_path,
            dataset_store=self._dataset_store,
            snapshot_store=self._snapshot_store,
            ledger=self._ledger,
            include_l2=include_l2,
        )

    async def _collect_and_compact(
        self,
        start_date: date,
        end_date: date,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        include_l2: bool,
    ) -> IndustryArtifacts:
        taxonomy_table = await self._provider.query(
            "index_classify",
            params={"level": "L1", "src": "SW2021"},
            fields=TAXONOMY_FIELDS,
        )
        self._preserve_raw(taxonomy_table)
        taxonomy_tables = [taxonomy_table]
        taxonomy = list(normalize_taxonomy(taxonomy_table))
        if len(taxonomy) != 31:
            raise ValueError(f"SW2021 一级行业数量异常：{len(taxonomy)}，期望 31")
        if include_l2:
            l2_table = await self._provider.query(
                "index_classify",
                params={"level": "L2", "src": "SW2021"},
                fields=TAXONOMY_FIELDS,
            )
            self._preserve_raw(l2_table)
            taxonomy_tables.append(l2_table)
            l2 = canonicalize_l2_parents(taxonomy, normalize_taxonomy(l2_table, level="L2"))
            taxonomy.extend(l2)
        taxonomy_path = staging / "taxonomy.parquet"
        write_bytes_atomic(taxonomy_path, self._encoder.encode(taxonomy, INDUSTRY_TAXONOMY_COLUMNS))
        for table in taxonomy_tables:
            level = str(table.rows[0].get("level", "")) if table.rows else "unknown"
            self._record_request(state, state_path, table, taxonomy_path, f"taxonomy-{level}")

        for industry in taxonomy:
            for is_current in (True, False):
                await self._collect_membership(
                    industry.industry_code,
                    industry.industry_name,
                    is_current,
                    staging,
                    state,
                    state_path,
                    industry.level,
                )
            for window_start, window_end in five_year_windows(start_date, end_date):
                await self._collect_daily(
                    industry.industry_code,
                    industry.industry_name,
                    window_start,
                    window_end,
                    staging,
                    state,
                    state_path,
                    industry.level,
                )

        membership_path = staging / "industry_membership.parquet"
        membership_stats = self._compact(
            state,
            "index_member_all",
            membership_path,
            ("industry_code", "instrument_id", "effective_from", "source_record_hash"),
            "effective_from",
            ("level", "industry_code", "instrument_id", "effective_from", "effective_to"),
        )
        membership_stats.update(membership_overlap_stats(membership_path))
        daily_path = staging / "industry_index_daily.parquet"
        daily_stats = self._compact(
            state,
            "sw_daily",
            daily_path,
            ("trade_date", "industry_code", "source_record_hash"),
            "trade_date",
            ("level", "industry_code", "trade_date"),
        )
        return IndustryArtifacts(
            taxonomy_path=taxonomy_path,
            membership_path=membership_path,
            daily_path=daily_path,
            taxonomy_rows=len(taxonomy),
            membership_stats=membership_stats,
            daily_stats=daily_stats,
        )

    async def _collect_membership(
        self,
        code: str,
        name: str,
        is_current: bool,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        level: Literal["L1", "L2"],
    ) -> None:
        status = "Y" if is_current else "N"
        key = f"{level}-{code}-{status}"
        if self._request_intact(state, "index_member_all", key):
            return
        table = await self._provider.query(
            "index_member_all",
            params={
                "l1_code" if level == "L1" else "l2_code": code,
                "is_new": status,
            },
            fields=MEMBERSHIP_FIELDS,
        )
        if len(table.rows) >= 2_000:
            raise ValueError(f"index_member_all:{key} 达到提供方上限")
        self._preserve_raw(table)
        rows = normalize_memberships(
            table,
            industry_code=code,
            industry_name=name,
            is_current=is_current,
            level=level,
        )
        path = staging / "requests" / "index_member_all" / f"{key}.parquet"
        write_bytes_atomic(path, self._encoder.encode(rows, INDUSTRY_MEMBERSHIP_COLUMNS))
        self._record_request(state, state_path, table, path, key)

    async def _collect_daily(
        self,
        code: str,
        name: str,
        start: date,
        end: date,
        staging: Path,
        state: dict[str, object],
        state_path: Path,
        level: Literal["L1", "L2"],
    ) -> None:
        key = f"{level}-{code}-{start:%Y%m%d}-{end:%Y%m%d}"
        if self._request_intact(state, "sw_daily", key):
            return
        table = await self._provider.query(
            "sw_daily",
            params={"ts_code": code, "start_date": f"{start:%Y%m%d}", "end_date": f"{end:%Y%m%d}"},
            fields=INDEX_DAILY_FIELDS,
        )
        if len(table.rows) >= 5_000:
            raise ValueError(f"sw_daily:{key} 达到提供方上限")
        self._preserve_raw(table)
        rows = normalize_index_daily(table, industry_name=name, level=level)
        path = staging / "requests" / "sw_daily" / f"{key}.parquet"
        write_bytes_atomic(path, self._encoder.encode(rows, INDUSTRY_INDEX_DAILY_COLUMNS))
        self._record_request(state, state_path, table, path, key)

    def _preserve_raw(self, table: ProviderTable) -> None:
        envelope = RawRecordEnvelope(
            provider="tushare",
            interface_name=table.api_name,
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw_store.append(envelope, table.raw_body)

    def _record_request(
        self,
        state: dict[str, object],
        state_path: Path,
        table: ProviderTable,
        path: Path,
        key: str,
    ) -> None:
        requests = state["requests"]
        assert isinstance(requests, dict)
        requests[f"{table.api_name}:{key}"] = {
            "api_name": table.api_name,
            "key": key,
            "path": str(path),
            "hash": file_hash(path),
            "rows": len(table.rows),
            "received_at": table.received_at.isoformat(),
        }
        save_state(state_path, state)

    def _request_intact(self, state: dict[str, object], api_name: str, key: str) -> bool:
        requests = state["requests"]
        assert isinstance(requests, dict)
        value = requests.get(f"{api_name}:{key}")
        if not isinstance(value, dict):
            return False
        path = Path(str(value.get("path", "")))
        return path.is_file() and file_hash(path) == value.get("hash")

    def _compact(
        self,
        state: dict[str, object],
        api_name: str,
        output: Path,
        order_by: tuple[str, ...],
        date_column: str,
        identity_columns: tuple[str, ...],
    ) -> dict[str, object]:
        requests = state["requests"]
        assert isinstance(requests, dict)
        sources = tuple(
            sorted(
                Path(str(value["path"]))
                for value in requests.values()
                if isinstance(value, dict)
                and value.get("api_name") == api_name
                and self._request_intact(state, api_name, str(value["key"]))
            )
        )
        return self._compactor.compact(
            source_files=sources,
            output=output,
            order_by=order_by,
            date_column=date_column,
            identity_columns=identity_columns,
        )

    def _requests(self, state: dict[str, object]) -> dict[object, object]:
        requests = state["requests"]
        if not isinstance(requests, dict):
            raise ValueError("行业回填请求状态无效")
        return requests

    def _manifests(self, snapshot: DataSnapshot) -> dict[str, DatasetManifest]:
        result = {}
        for ref in snapshot.datasets:
            digest = ref.dataset_version.rsplit(":", 1)[-1]
            path = self._root / "datasets" / ref.dataset_name / digest / "manifest.json"
            result[ref.dataset_name] = DatasetManifest.model_validate_json(
                path.read_text(encoding="utf-8")
            )
        return result

    def _completed(
        self, snapshot_id: str, state: dict[str, object]
    ) -> IndustryFoundationPublication:
        snapshot = self._snapshot_store.get(snapshot_id)
        manifests = self._manifests(snapshot)
        selected = tuple(
            manifests[name]
            for name in ("industry_taxonomy", "industry_membership", "industry_index_daily")
        )
        return IndustryFoundationPublication(snapshot, selected, len(self._requests(state)))


__all__ = ["IndustryFoundationPublication", "IndustryFoundationService"]
