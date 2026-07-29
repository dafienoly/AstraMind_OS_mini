"""Read the trading calendar and completed-day identity from the current snapshot."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import duckdb

from ..application.market_session_status import MarketSessionContext
from ..contracts.provider import DatasetManifest

_COMPLETED_MARKET_DATASETS = (
    "broad_index_daily",
    "daily_market",
    "industry_index_daily",
)


class SnapshotMarketSessionContext:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root
        self._cached: tuple[tuple[int, int], date, MarketSessionContext] | None = None

    def read(self, *, today: date) -> MarketSessionContext:
        pointer = self._root / "current" / "data-snapshot.json"
        stat = pointer.stat()
        revision = (stat.st_mtime_ns, stat.st_size)
        if self._cached is not None and self._cached[:2] == (revision, today):
            return self._cached[2]
        references = self._snapshot_references()
        calendar = self._manifest("trade_calendar", references)
        calendar_paths = self._artifact_paths("trade_calendar", calendar)
        lower = today - timedelta(days=90)
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT calendar_date
                FROM read_parquet(?)
                WHERE exchange = 'SSE' AND is_open
                  AND calendar_date BETWEEN ? AND ?
                ORDER BY calendar_date
                """,
                [[str(path) for path in calendar_paths], lower, today],
            ).fetchall()
        completed = min(
            self._manifest(name, references).date_range[1] for name in _COMPLETED_MARKET_DATASETS
        )
        result = MarketSessionContext(
            open_dates=tuple(row[0] for row in rows if isinstance(row[0], date)),
            latest_completed_trade_date=completed,
        )
        self._cached = (revision, today, result)
        return result

    def read_if_available(self, *, today: date) -> MarketSessionContext | None:
        try:
            return self.read(today=today)
        except (FileNotFoundError, KeyError, ValueError, OSError, duckdb.Error):
            return None

    def _snapshot_references(self) -> dict[str, tuple[str, str]]:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        snapshot_id = str(pointer["snapshot_id"])
        snapshot = json.loads(
            (
                self._root / "snapshots" / _digest(snapshot_id, "snapshot:sha256") / "manifest.json"
            ).read_text(encoding="utf-8")
        )
        return {
            str(item["dataset_name"]): (
                str(item["dataset_version"]),
                str(item["content_hash"]),
            )
            for item in snapshot["datasets"]
        }

    def _manifest(
        self,
        name: str,
        references: dict[str, tuple[str, str]],
    ) -> DatasetManifest:
        version, expected_hash = references[name]
        path = self._root / "datasets" / name / _digest(version, "sha256") / "manifest.json"
        manifest = DatasetManifest.model_validate_json(path.read_text(encoding="utf-8"))
        if manifest.dataset_version != version or manifest.content_hash != expected_hash:
            raise ValueError(f"市场会话数据集身份冲突：{name}")
        return manifest

    def _artifact_paths(
        self,
        name: str,
        manifest: DatasetManifest,
    ) -> tuple[Path, ...]:
        directory = self._root / "datasets" / name / _digest(manifest.dataset_version, "sha256")
        paths = tuple(
            directory / item for item in manifest.artifact_paths if item.endswith(".parquet")
        )
        if not paths or any(not path.is_file() for path in paths):
            raise ValueError(f"市场会话数据集制品缺失：{name}")
        return paths


def _digest(identity: str, prefix: str) -> str:
    value = identity.removeprefix(prefix + ":")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


__all__ = ["SnapshotMarketSessionContext"]
