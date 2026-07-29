"""Build a page projection from one exact immutable DataSnapshot."""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..contracts.dashboard import MarketDashboardProjection
from ..domain.dashboard import PROJECTION_VERSION, describe_regime
from .dashboard_heat import industry_heat
from .dashboard_queries import index_views, market_totals

REQUIRED_DATASETS = (
    "broad_index_daily",
    "daily_market",
    "daily_tradability",
    "industry_index_daily",
    "industry_membership",
    "trade_calendar",
)


class SnapshotMarketDashboard:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(self) -> MarketDashboardProjection:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        if not isinstance(pointer, dict) or not isinstance(pointer.get("snapshot_id"), str):
            raise ValueError("当前数据快照指针无效")
        return self.load(pointer["snapshot_id"])

    def load(self, snapshot_id: str) -> MarketDashboardProjection:
        snapshot = self._snapshot(snapshot_id)
        references = {item.dataset_name: item for item in snapshot.datasets}
        missing = tuple(name for name in REQUIRED_DATASETS if name not in references)
        if missing:
            return MarketDashboardProjection(
                status="blocked",
                data_snapshot_id=snapshot.snapshot_id,
                as_of=snapshot.as_of,
                projection_version=PROJECTION_VERSION,
                known_gaps=tuple(f"missing_dataset:{name}" for name in missing),
            )
        paths = {
            name: self._paths(name, references[name].dataset_version, references[name].content_hash)
            for name in REQUIRED_DATASETS
        }
        cutoff = self._cutoff(paths)
        with duckdb.connect(":memory:") as connection:
            indexes = index_views(connection, paths["broad_index_daily"], cutoff)
            breadth, liquidity = market_totals(connection, paths, cutoff)
            industries = industry_heat(connection, paths, cutoff)
        gaps = []
        expected = {
            "000001.SH",
            "399001.SZ",
            "399006.SZ",
            "000688.SH",
            "000300.SH",
            "000852.SH",
        }
        if {item.instrument_id for item in indexes} != expected:
            gaps.append("broad_index_registry_incomplete")
        if len(industries) != 31:
            gaps.append(f"industry_l1_count:{len(industries)}/31")
        benchmark = next(
            (item for item in indexes if item.instrument_id == "000300.SH"),
            None,
        )
        if gaps or benchmark is None:
            return MarketDashboardProjection(
                status="blocked",
                data_snapshot_id=snapshot.snapshot_id,
                as_of=snapshot.as_of,
                evidence_cutoff=cutoff,
                projection_version=PROJECTION_VERSION,
                indexes=indexes,
                breadth=breadth,
                liquidity=liquidity,
                industries=industries,
                known_gaps=tuple(gaps),
            )
        regime = describe_regime(
            index_return_20d=benchmark.return_20d,
            advance_ratio=breadth.advance_ratio,
            amount_change_20d=liquidity.amount_change_20d,
        )
        expected_cutoff = self._expected_cutoff(paths["trade_calendar"], snapshot.as_of)
        stale = cutoff < expected_cutoff
        return MarketDashboardProjection(
            status="stale" if stale else "ready",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of,
            evidence_cutoff=cutoff,
            projection_version=PROJECTION_VERSION,
            selected_index_id="000300.SH",
            indexes=indexes,
            breadth=breadth,
            liquidity=liquidity,
            regime=regime,
            industries=industries,
            known_gaps=("snapshot_cutoff_before_as_of_date",) if stale else (),
        )

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = _digest(snapshot_id, "snapshot:sha256")
        snapshot = DataSnapshot.model_validate_json(
            (self._root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
        )
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("大盘投影快照身份与路径不一致")
        return snapshot

    def _paths(self, name: str, version: str, content_hash: str) -> tuple[Path, ...]:
        digest = _digest(version, "sha256")
        directory = self._root / "datasets" / name / digest
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest.get("dataset_version") != version
            or manifest.get("content_hash") != content_hash
        ):
            raise ValueError(f"大盘投影数据集身份冲突：{name}")
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"大盘投影数据集制品无效：{name}")
        paths = tuple(directory / str(item) for item in artifacts if str(item).endswith(".parquet"))
        if not paths or any(not item.is_file() for item in paths):
            raise ValueError(f"大盘投影数据集制品缺失：{name}")
        return paths

    def _cutoff(self, paths: dict[str, tuple[Path, ...]]) -> date:
        with duckdb.connect(":memory:") as connection:
            row = connection.execute(
                """
                SELECT least(
                  (SELECT max(trade_date) FROM read_parquet(?)),
                  (SELECT max(trade_date) FROM read_parquet(?)),
                  (SELECT max(trade_date) FROM read_parquet(?))
                )
                """,
                [
                    [str(item) for item in paths["broad_index_daily"]],
                    [str(item) for item in paths["daily_market"]],
                    [str(item) for item in paths["industry_index_daily"]],
                ],
            ).fetchone()
        if row is None or not isinstance(row[0], date):
            raise ValueError("大盘投影没有共同证据截止日")
        return row[0]

    def _expected_cutoff(self, paths: tuple[Path, ...], as_of: object) -> date:
        if not hasattr(as_of, "astimezone"):
            raise ValueError("大盘投影快照时间无效")
        local = as_of.astimezone(ZoneInfo("Asia/Shanghai"))
        upper = local.date()
        if local.time() < time(18):
            upper = date.fromordinal(upper.toordinal() - 1)
        with duckdb.connect(":memory:") as connection:
            row = connection.execute(
                """
                SELECT max(calendar_date) FROM read_parquet(?)
                WHERE exchange = 'SSE' AND is_open AND calendar_date <= ?
                """,
                [[str(item) for item in paths], upper],
            ).fetchone()
        if row is None or not isinstance(row[0], date):
            raise ValueError("大盘投影无法解析预期完成交易日")
        return row[0]


def _digest(identity: str, prefix: str) -> str:
    value = identity.removeprefix(prefix + ":")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


__all__ = ["SnapshotMarketDashboard"]
