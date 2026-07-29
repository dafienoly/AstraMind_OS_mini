"""Resumable, read-only coverage probe for pre-2007 Tushare price limits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts import DatasetManifest, RawRecordEnvelope
from ..ports import HistoricalMarketDataProvider, ParquetEncoder, RawRecordStore
from .dataset_schemas import PRICE_LIMIT_COLUMNS
from .event_backfill_support import artifact_paths
from .identity import canonical_json, content_hash, file_hash
from .normalization import normalize_price_limits
from .publication_policy import PRICE_LIMIT_FIELDS
from .state_files import load_state, save_state, write_bytes_atomic


@dataclass(frozen=True, slots=True)
class HistoricalPriceLimitProbe:
    probe_id: str
    start_date: date
    end_date: date
    expected_sessions: int
    observed_sessions: int
    empty_sessions: tuple[date, ...]
    total_rows: int
    state: str
    artifact_path: Path


class HistoricalPriceLimitProbeService:
    def __init__(
        self,
        *,
        data_root: Path,
        provider: HistoricalMarketDataProvider,
        raw_store: RawRecordStore,
        encoder: ParquetEncoder,
    ) -> None:
        self._root = data_root
        self._provider = provider
        self._raw = raw_store
        self._encoder = encoder

    async def run(
        self,
        *,
        base_snapshot_id: str,
        start_date: date,
        end_date: date,
    ) -> HistoricalPriceLimitProbe:
        if start_date > end_date:
            raise ValueError("涨跌停探测开始日期不能晚于结束日期")
        snapshot = self._snapshot(base_snapshot_id)
        calendar = self._manifest(snapshot, "trade_calendar")
        sessions = self._trade_dates(calendar, start_date, end_date)
        probe_id = content_hash(
            {
                "base_snapshot_id": base_snapshot_id,
                "calendar_version": calendar.dataset_version,
                "start_date": start_date,
                "end_date": end_date,
                "policy": "pre-2007-price-limit-probe-v1",
            }
        )
        staging = self._root / "imports" / probe_id.rsplit(":", 1)[-1]
        state_path = staging / "state.json"
        state = load_state(state_path) or {
            "probe_id": probe_id,
            "requests": {},
        }
        for index, trade_date in enumerate(sessions, start=1):
            await self._collect(trade_date, staging, state)
            if index % 16 == 0:
                save_state(state_path, state)
        save_state(state_path, state)
        return self._report(
            probe_id=probe_id,
            start_date=start_date,
            end_date=end_date,
            sessions=sessions,
            state=state,
        )

    async def _collect(
        self,
        trade_date: date,
        staging: Path,
        state: dict[str, object],
    ) -> None:
        requests = state["requests"]
        assert isinstance(requests, dict)
        key = trade_date.isoformat()
        cached = requests.get(key)
        if isinstance(cached, dict):
            path = Path(str(cached.get("path", "")))
            if path.is_file() and file_hash(path) == cached.get("hash"):
                return
        compact = trade_date.strftime("%Y%m%d")
        table = await self._provider.query(
            "stk_limit",
            params={"trade_date": compact},
            fields=PRICE_LIMIT_FIELDS,
        )
        envelope = RawRecordEnvelope(
            provider="tushare",
            interface_name="stk_limit",
            source_endpoint=table.source_endpoint,
            request_identity=table.request_identity,
            received_at=table.received_at,
            schema_version="provider-v1",
            content_hash=content_hash(table.raw_body),
        )
        self._raw.append(envelope, table.raw_body)
        rows = normalize_price_limits(table)
        if any(row.trade_date != trade_date for row in rows):
            raise ValueError(f"stk_limit:{trade_date} 返回请求范围外记录")
        identities = {(row.instrument_id, row.trade_date) for row in rows}
        if len(identities) != len(rows):
            raise ValueError(f"stk_limit:{trade_date} 返回重复主键")
        path = staging / "requests" / f"{compact}.parquet"
        write_bytes_atomic(path, self._encoder.encode(rows, PRICE_LIMIT_COLUMNS))
        requests[key] = {
            "path": str(path),
            "hash": file_hash(path),
            "rows": len(rows),
            "request_identity": table.request_identity,
            "received_at": table.received_at.isoformat(),
        }

    def _report(
        self,
        *,
        probe_id: str,
        start_date: date,
        end_date: date,
        sessions: tuple[date, ...],
        state: dict[str, object],
    ) -> HistoricalPriceLimitProbe:
        requests = state["requests"]
        assert isinstance(requests, dict)
        empty = tuple(value for value in sessions if _rows(_request(requests, value)) == 0)
        total_rows = sum(_rows(_request(requests, value)) for value in sessions)
        status = "backfill_ready" if not empty else "historical_unavailable"
        report = {
            "probe_id": probe_id,
            "provider": "tushare",
            "endpoint": "stk_limit",
            "date_range": [start_date, end_date],
            "expected_sessions": len(sessions),
            "observed_sessions": len(requests),
            "empty_sessions": empty,
            "total_rows": total_rows,
            "state": status,
            "publish_price_limit": False,
            "broker_actions_allowed": False,
        }
        path = (
            self._root
            / "provider-probes"
            / "tushare"
            / "historical-price-limit"
            / f"{probe_id.rsplit(':', 1)[-1]}.json"
        )
        write_bytes_atomic(path, canonical_json(report))
        return HistoricalPriceLimitProbe(
            probe_id=probe_id,
            start_date=start_date,
            end_date=end_date,
            expected_sessions=len(sessions),
            observed_sessions=len(requests),
            empty_sessions=empty,
            total_rows=total_rows,
            state=status,
            artifact_path=path,
        )

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = snapshot_id.rsplit(":", 1)[-1]
        path = self._root / "snapshots" / digest / "manifest.json"
        snapshot = DataSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("涨跌停探测基础快照身份冲突")
        return snapshot

    def _manifest(self, snapshot: DataSnapshot, name: str) -> DatasetManifest:
        reference = next((item for item in snapshot.datasets if item.dataset_name == name), None)
        if reference is None:
            raise ValueError(f"基础快照缺少 {name}")
        digest = reference.dataset_version.rsplit(":", 1)[-1]
        path = self._root / "datasets" / name / digest / "manifest.json"
        manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if manifest.dataset_version != reference.dataset_version:
            raise ValueError(f"{name} 快照引用与清单冲突")
        return manifest

    def _trade_dates(
        self,
        manifest: DatasetManifest,
        start_date: date,
        end_date: date,
    ) -> tuple[date, ...]:
        paths = artifact_paths(self._root, manifest)
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT calendar_date FROM read_parquet(?)
                WHERE exchange = 'SSE' AND is_open
                  AND calendar_date BETWEEN ? AND ?
                ORDER BY calendar_date
                """,
                [[str(path) for path in paths], start_date, end_date],
            ).fetchall()
        if not rows:
            raise ValueError("涨跌停探测区间没有交易日")
        return tuple(row[0] for row in rows)


def _request(requests: dict[object, object], value: date) -> dict[str, object]:
    item = requests.get(value.isoformat())
    if not isinstance(item, dict):
        raise ValueError(f"缺少涨跌停探测分区：{value}")
    return item


def _rows(item: dict[str, object]) -> int:
    value = item.get("rows")
    if not isinstance(value, int):
        raise ValueError("涨跌停探测分区行数无效")
    return value


__all__ = ["HistoricalPriceLimitProbe", "HistoricalPriceLimitProbeService"]
