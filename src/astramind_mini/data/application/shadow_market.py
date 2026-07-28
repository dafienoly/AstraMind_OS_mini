"""Read daily Shadow evidence from one exact immutable DataSnapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal, cast

import duckdb

from ..contracts.shadow_market import ShadowMarketObservation


class SnapshotShadowMarketReader:
    _REQUIRED = ("daily_market", "daily_tradability", "trade_calendar")

    def __init__(self, data_root: Path, snapshot_id: str) -> None:
        self._root = data_root
        self.snapshot_id = snapshot_id
        digest = snapshot_id.rsplit(":", 1)[-1]
        path = data_root / "snapshots" / digest / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"快照不存在：{snapshot_id}")
        snapshot = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        if snapshot.get("snapshot_id") != snapshot_id:
            raise ValueError("Shadow 行情快照身份与路径不一致")
        datasets = cast(list[dict[str, object]], snapshot.get("datasets", []))
        versions = {str(item["dataset_name"]): str(item["dataset_version"]) for item in datasets}
        missing = sorted(set(self._REQUIRED) - versions.keys())
        if missing:
            raise ValueError("Shadow 行情快照缺少数据集：" + ",".join(missing))
        self._paths_by_name = {
            name: self._manifest_paths(name, versions[name]) for name in self._REQUIRED
        }

    def trading_dates(self, *, start_date: date, end_date: date) -> tuple[date, ...]:
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT calendar_date
                FROM read_parquet(?)
                WHERE exchange = 'SSE' AND is_open
                  AND calendar_date BETWEEN ? AND ?
                ORDER BY calendar_date
                """,
                [self._paths("trade_calendar"), start_date, end_date],
            ).fetchall()
        return tuple(row[0] for row in rows)

    def observations(
        self,
        *,
        instruments: tuple[str, ...],
        trade_date: date,
    ) -> tuple[ShadowMarketObservation, ...]:
        if not instruments:
            return ()
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT t.instrument_id, t.trade_date,
                       greatest(t.available_at, d.available_at),
                       d.open, d.close, d.amount_thousand_cny * 1000,
                       t.buy_state, t.sell_state, t.has_daily_bar
                FROM read_parquet(?) t
                LEFT JOIN read_parquet(?) d USING (instrument_id, trade_date)
                WHERE t.instrument_id IN (SELECT unnest(?))
                  AND t.trade_date = ?
                ORDER BY t.instrument_id
                """,
                [
                    self._paths("daily_tradability"),
                    self._paths("daily_market"),
                    list(instruments),
                    trade_date,
                ],
            ).fetchall()
        return tuple(
            ShadowMarketObservation(
                data_snapshot_id=self.snapshot_id,
                instrument_id=str(row[0]),
                trade_date=row[1],
                available_at=row[2],
                open_price=float(row[3]) if row[3] is not None else None,
                close_price=float(row[4]) if row[4] is not None else None,
                amount_cny=float(row[5]) if row[5] is not None else 0,
                buy_state=cast(
                    Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"],
                    str(row[6]),
                ),
                sell_state=cast(
                    Literal["tradable", "limit_locked", "suspended", "no_bar", "unknown_limit"],
                    str(row[7]),
                ),
                has_daily_bar=bool(row[8]),
            )
            for row in rows
        )

    def _manifest_paths(self, name: str, version: str) -> tuple[str, ...]:
        digest = version.rsplit(":", 1)[-1]
        base = self._root / "datasets" / name / digest
        path = base / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Shadow 数据集清单不存在：{name}")
        manifest = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        if manifest.get("dataset_version") != version:
            raise ValueError(f"Shadow 数据集版本身份不一致：{name}")
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"Shadow 数据集制品清单无效：{name}")
        paths = tuple(
            str(base / item)
            for item in artifacts
            if isinstance(item, str) and item.endswith(".parquet")
        )
        if not paths or any(not Path(item).is_file() for item in paths):
            raise ValueError(f"Shadow 数据集声明的精确 Parquet 不完整：{name}")
        return paths

    def _paths(self, name: str) -> list[str]:
        return list(self._paths_by_name[name])


__all__ = ["SnapshotShadowMarketReader"]
