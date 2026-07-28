"""Full-universe replay reader constrained to one immutable snapshot."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

import duckdb

from ..domain.backtest_models import CandidateSignal
from ..domain.sealed_models import CurrentSignalCandidate, ReplayCandidate, ReplayPrice
from .sealed_snapshot_query import CANDIDATE_SQL, CURRENT_SIGNAL_SQL

_FAMILIES = {"event_attention", "momentum_breakout", "reversal_volume_price"}


class DuckDBSealedReplaySource:
    def __init__(self, data_root: Path, snapshot_id: str) -> None:
        self._root = data_root
        digest = snapshot_id.rsplit(":", 1)[-1]
        path = data_root / "snapshots" / digest / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"快照不存在：{snapshot_id}")
        snapshot = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        if snapshot.get("snapshot_id") != snapshot_id:
            raise ValueError("快照身份与路径不一致")
        datasets = snapshot.get("datasets")
        if not isinstance(datasets, list):
            raise ValueError("快照数据集引用无效")
        self._manifests = {
            str(item["dataset_name"]): self._load_manifest(
                str(item["dataset_name"]), str(item["dataset_version"])
            )
            for item in datasets
            if isinstance(item, dict)
        }

    def trading_dates(self, *, start_date: date, end_date: date) -> tuple[date, ...]:
        self._validate_window(start_date, end_date)
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT DISTINCT trade_date
                FROM read_parquet(?)
                WHERE trade_date BETWEEN ? AND ?
                ORDER BY trade_date
                """,
                [self._paths("daily_market"), start_date, end_date],
            ).fetchall()
        return tuple(row[0] for row in rows)

    def latest_trading_date(self) -> date:
        with duckdb.connect(":memory:") as connection:
            row = connection.execute(
                "SELECT max(trade_date) FROM read_parquet(?)",
                [self._paths("daily_market")],
            ).fetchone()
        if row is None or row[0] is None:
            raise ValueError("快照日线数据为空")
        return cast(date, row[0])

    def candidates(
        self,
        *,
        family: str,
        horizon_sessions: int,
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayCandidate, ...]:
        if family not in _FAMILIES:
            raise ValueError(f"未知策略家族：{family}")
        if horizon_sessions not in {2, 5, 10}:
            raise ValueError("封存周期只能为 2/5/10 个交易日")
        self._validate_window(start_date, end_date)
        if family == "event_attention":
            for dataset in ("lhb_event", "lhb_seat"):
                if dataset not in self._manifests:
                    raise ValueError(f"事件策略所需数据集缺失：{dataset}")
        with duckdb.connect(":memory:") as connection:
            self._event_view(connection)
            rows = connection.execute(
                CANDIDATE_SQL,
                [
                    self._paths("daily_tradability"),
                    end_date,
                    self._paths("daily_market"),
                    self._paths("adjusted_market"),
                    start_date,
                    family,
                    family,
                    family,
                    family,
                    family,
                    start_date,
                    end_date,
                    horizon_sessions,
                    end_date,
                ],
            ).fetchall()
        return tuple(self._candidate(family, horizon_sessions, row) for row in rows)

    def prices(
        self,
        *,
        instruments: tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayPrice, ...]:
        if not instruments:
            return ()
        self._validate_window(start_date, end_date)
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                SELECT instrument_id, trade_date, close
                FROM read_parquet(?)
                WHERE instrument_id IN (SELECT unnest(?))
                  AND trade_date BETWEEN ? AND ?
                ORDER BY instrument_id, trade_date
                """,
                [self._paths("daily_market"), list(instruments), start_date, end_date],
            ).fetchall()
        return tuple(ReplayPrice(*row) for row in rows)

    def current_signals(
        self,
        *,
        family: str,
        horizon_sessions: int,
        signal_date: date,
    ) -> tuple[CurrentSignalCandidate, ...]:
        if family != "reversal_volume_price":
            raise ValueError("当前信号扫描仅支持已晋级的 reversal_volume_price")
        if horizon_sessions != 10:
            raise ValueError("当前已晋级策略周期必须为 10 个交易日")
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                CURRENT_SIGNAL_SQL,
                [
                    self._paths("daily_tradability"),
                    signal_date,
                    self._paths("daily_market"),
                    self._paths("adjusted_market"),
                    signal_date,
                    signal_date,
                ],
            ).fetchall()
        return tuple(
            CurrentSignalCandidate(
                signal=CandidateSignal(
                    instrument_id=str(instrument),
                    signal_date=cast(date, observed_date),
                    family=family,
                    horizon_sessions=horizon_sessions,
                    score=float(cast(float, score)),
                    reasons=(
                        f"return_5d={float(cast(float, return_5)):.6f}",
                        f"daily_rebound={float(cast(float, return_1)):.6f}",
                        f"amount_ratio={float(cast(float, amount_ratio)):.6f}",
                    ),
                ),
                reference_price=float(cast(float, close)),
            )
            for (
                instrument,
                observed_date,
                score,
                close,
                return_5,
                return_1,
                amount_ratio,
            ) in rows
        )

    def _event_view(self, connection: duckdb.DuckDBPyConnection) -> None:
        event_paths = self._optional_paths("lhb_event")
        seat_paths = self._optional_paths("lhb_seat")
        if event_paths:
            connection.execute(
                "CREATE TEMP TABLE lhb_source AS SELECT * FROM read_parquet(?)",
                [event_paths],
            )
        else:
            connection.execute(
                """
                CREATE TEMP TABLE lhb_source (
                  instrument_id VARCHAR, trade_date DATE, available_at TIMESTAMPTZ,
                  net_rate DOUBLE
                )
                """
            )
        if seat_paths:
            connection.execute(
                "CREATE TEMP TABLE seat_source AS SELECT * FROM read_parquet(?)",
                [seat_paths],
            )
        else:
            connection.execute(
                """
                CREATE TEMP TABLE seat_source (
                  instrument_id VARCHAR, trade_date DATE, available_at TIMESTAMPTZ,
                  seat_name VARCHAR, reason VARCHAR, net_buy_cny DOUBLE
                )
                """
            )
        connection.execute(
            """
            CREATE TEMP VIEW event_context AS
            WITH events AS (
              SELECT instrument_id, trade_date, count(*) AS event_count,
                     sum(net_rate) AS net_rate
              FROM lhb_source
              WHERE available_at <= timezone(
                'Asia/Shanghai', CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
              )
              GROUP BY instrument_id, trade_date
            ), seat_records AS (
              SELECT instrument_id, trade_date, seat_name, reason, max(net_buy_cny) AS net_buy_cny
              FROM seat_source
              WHERE available_at <= timezone(
                'Asia/Shanghai', CAST(trade_date AS TIMESTAMP) + INTERVAL '18 hours'
              )
              GROUP BY instrument_id, trade_date, seat_name, reason
            ), seats AS (
              SELECT instrument_id, trade_date, sum(net_buy_cny) AS institutional_net
              FROM seat_records GROUP BY instrument_id, trade_date
            )
            SELECT e.*, s.institutional_net
            FROM events e LEFT JOIN seats s USING (instrument_id, trade_date)
            """
        )

    def _load_manifest(self, name: str, version: str) -> dict[str, object]:
        digest = version.rsplit(":", 1)[-1]
        path = self._root / "datasets" / name / digest / "manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"快照数据集清单不存在：{name}")
        manifest = cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))
        if manifest.get("dataset_version") != version:
            raise ValueError(f"数据集版本身份不一致：{name}")
        if manifest.get("publish_status") != "complete":
            raise ValueError(f"数据集未完整发布：{name}")
        if manifest.get("critical_gaps"):
            raise ValueError(f"数据集存在关键缺口：{name}")
        return manifest

    def _paths(self, name: str) -> list[str]:
        manifest = self._manifests.get(name)
        if manifest is None:
            raise ValueError(f"快照缺少封存数据集：{name}")
        digest = str(manifest["dataset_version"]).rsplit(":", 1)[-1]
        base = self._root / "datasets" / name / digest
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"数据集制品清单无效：{name}")
        paths = [
            str(base / artifact)
            for artifact in artifacts
            if isinstance(artifact, str) and artifact.endswith(".parquet")
        ]
        if not paths or any(not Path(path).is_file() for path in paths):
            raise ValueError(f"数据集声明的精确 Parquet 不完整：{name}")
        return paths

    def _optional_paths(self, name: str) -> list[str]:
        return self._paths(name) if name in self._manifests else []

    @staticmethod
    def _validate_window(start_date: date, end_date: date) -> None:
        if start_date > end_date:
            raise ValueError("封存窗口起止日期无效")

    @staticmethod
    def _candidate(family: str, horizon_sessions: int, row: tuple[object, ...]) -> ReplayCandidate:
        (
            instrument,
            signal_date,
            score,
            event_count,
            net_rate,
            institutional_net,
            entry_date,
            entry_open,
            entry_amount,
            entry_buy_state,
            target_exit_date,
            exit_date,
            exit_open,
        ) = row
        reasons = _reasons(family, event_count, net_rate, institutional_net)
        return ReplayCandidate(
            signal=CandidateSignal(
                instrument_id=str(instrument),
                signal_date=cast(date, signal_date),
                family=family,
                horizon_sessions=horizon_sessions,
                score=float(cast(float, score)),
                reasons=reasons,
            ),
            entry_date=cast(date, entry_date),
            entry_open=cast(float | None, entry_open),
            entry_amount_cny=cast(float | None, entry_amount),
            entry_buy_state=cast(str | None, entry_buy_state),
            target_exit_date=cast(date | None, target_exit_date),
            exit_date=cast(date | None, exit_date),
            exit_open=cast(float | None, exit_open),
        )


def _reasons(
    family: str, event_count: object, net_rate: object, institutional_net: object
) -> tuple[str, ...]:
    if family != "event_attention":
        return (f"frozen_signal={family}:v1",)
    count = int(cast(int, event_count or 0))
    rate = float(cast(float, net_rate or 0))
    institutional = float(cast(float, institutional_net or 0))
    return (
        f"lhb_event_count={count}",
        f"lhb_net_rate={rate:.6f}",
        f"institutional_net_buy_cny={institutional:.2f}",
    )


__all__ = ["DuckDBSealedReplaySource"]
