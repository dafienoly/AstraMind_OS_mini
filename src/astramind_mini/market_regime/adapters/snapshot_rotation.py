"""Read exact industry datasets from one immutable DataSnapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..domain.rotation import IndustryCloseSeries


class SnapshotRotationInput:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def load(
        self, snapshot_id: str, *, required_sessions: int
    ) -> tuple[
        DataSnapshot,
        tuple[date, ...],
        tuple[IndustryCloseSeries, ...],
        tuple[str, ...],
    ]:
        snapshot = self._snapshot(snapshot_id)
        manifests = {
            name: self._manifest(snapshot, name)
            for name in (
                "industry_taxonomy",
                "industry_membership",
                "industry_index_daily",
                "trade_calendar",
            )
        }
        paths = {name: self._parquet_paths(manifest) for name, manifest in manifests.items()}
        with duckdb.connect(":memory:") as connection:
            industry_cutoff = self._latest_industry_date(connection, paths["industry_index_daily"])
            calendar = self._calendar(
                connection,
                paths["trade_calendar"],
                min(snapshot.as_of.date(), industry_cutoff),
                required_sessions,
            )
            names = self._taxonomy(connection, paths["industry_taxonomy"])
            closes = self._closes(connection, paths["industry_index_daily"], calendar)
            counts = self._constituent_counts(connection, paths["industry_membership"], calendar)
        industries = tuple(
            IndustryCloseSeries(
                industry_code=code,
                industry_name=names[code],
                closes=closes.get(code, {}),
                constituent_counts=counts.get(code, {}),
            )
            for code in sorted(names)
        )
        gaps = tuple(
            sorted(
                {
                    str(gap)
                    for name in ("industry_membership", "industry_index_daily")
                    for gap in _list(manifests[name].get("known_gaps"))
                }
            )
        )
        return snapshot, calendar, industries, gaps

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = _digest(snapshot_id, "snapshot:sha256")
        path = self._root / "snapshots" / digest / "manifest.json"
        snapshot = DataSnapshot.model_validate_json(path.read_text(encoding="utf-8"))
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("DataSnapshot 身份与路径不一致")
        return snapshot

    def _manifest(self, snapshot: DataSnapshot, dataset_name: str) -> dict[str, object]:
        references = {item.dataset_name: item for item in snapshot.datasets}
        reference = references.get(dataset_name)
        if reference is None:
            raise ValueError(f"轮动输入缺少数据集：{dataset_name}")
        digest = _digest(reference.dataset_version, "sha256")
        path = self._root / "datasets" / dataset_name / digest / "manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError(f"数据集清单无效：{dataset_name}")
        if (
            value.get("dataset_version") != reference.dataset_version
            or value.get("content_hash") != reference.content_hash
        ):
            raise ValueError(f"数据集清单身份冲突：{dataset_name}")
        return value

    def _parquet_paths(self, manifest: dict[str, object]) -> tuple[Path, ...]:
        dataset = str(manifest["dataset_name"])
        digest = _digest(str(manifest["dataset_version"]), "sha256")
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"数据集制品清单无效：{dataset}")
        paths = tuple(
            self._root / "datasets" / dataset / digest / str(name)
            for name in artifacts
            if str(name).endswith(".parquet")
        )
        if not paths or any(not path.is_file() for path in paths):
            raise ValueError(f"数据集精确 Parquet 不完整：{dataset}")
        return paths

    def _calendar(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
        as_of: date,
        required: int,
    ) -> tuple[date, ...]:
        rows = connection.execute(
            """
            SELECT DISTINCT calendar_date
            FROM read_parquet(?)
            WHERE exchange = 'SSE' AND is_open AND calendar_date <= ?
            ORDER BY calendar_date DESC LIMIT ?
            """,
            [[str(path) for path in paths], as_of, required],
        ).fetchall()
        dates = tuple(sorted(row[0] for row in rows))
        if len(dates) != required:
            raise ValueError(f"轮动交易日不足：{len(dates)}/{required}")
        return dates

    def _latest_industry_date(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
    ) -> date:
        row = connection.execute(
            """
            SELECT max(trade_date) FROM read_parquet(?)
            WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021' AND level = 'L1'
            """,
            [[str(path) for path in paths]],
        ).fetchone()
        if row is None or row[0] is None:
            raise ValueError("正式轮动行业日线为空")
        value = row[0]
        if not isinstance(value, date):
            raise ValueError("正式轮动行业日期类型无效")
        return value

    def _taxonomy(
        self, connection: duckdb.DuckDBPyConnection, paths: tuple[Path, ...]
    ) -> dict[str, str]:
        rows = connection.execute(
            """
            SELECT industry_code, industry_name FROM read_parquet(?)
            WHERE taxonomy = 'SW' AND taxonomy_version = 'SW2021' AND level = 'L1'
            ORDER BY industry_code
            """,
            [[str(path) for path in paths]],
        ).fetchall()
        result = {str(code): str(name) for code, name in rows}
        if len(result) != 31:
            raise ValueError(f"正式轮动要求 31 个 SW2021 一级行业，实际 {len(result)}")
        return result

    def _closes(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
        calendar: tuple[date, ...],
    ) -> dict[str, dict[date, float]]:
        rows = connection.execute(
            """
            SELECT industry_code, trade_date, close
            FROM read_parquet(?)
            WHERE trade_date BETWEEN ? AND ?
            ORDER BY industry_code, trade_date
            """,
            [[str(path) for path in paths], calendar[0], calendar[-1]],
        ).fetchall()
        result: dict[str, dict[date, float]] = {}
        for code, day, close in rows:
            result.setdefault(str(code), {})[day] = float(close)
        return result

    def _constituent_counts(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: tuple[Path, ...],
        calendar: tuple[date, ...],
    ) -> dict[str, dict[date, int]]:
        rows = connection.execute(
            """
            WITH dates AS (SELECT unnest(?::DATE[]) AS trade_date)
            SELECT m.industry_code, d.trade_date, count(DISTINCT m.instrument_id)
            FROM dates d JOIN read_parquet(?) m
              ON m.effective_from <= d.trade_date
             AND (m.effective_to IS NULL OR d.trade_date < m.effective_to)
             AND CAST(m.available_at AS DATE) <= d.trade_date
            GROUP BY m.industry_code, d.trade_date
            ORDER BY m.industry_code, d.trade_date
            """,
            [list(calendar), [str(path) for path in paths]],
        ).fetchall()
        result: dict[str, dict[date, int]] = {}
        for code, day, count in rows:
            result.setdefault(str(code), {})[day] = int(count)
        return result


def _digest(identity: str, prefix: str) -> str:
    expected = f"{prefix}:"
    value = identity.removeprefix(expected)
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


def _list(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("数据集缺口清单无效")
    return value


__all__ = ["SnapshotRotationInput"]
