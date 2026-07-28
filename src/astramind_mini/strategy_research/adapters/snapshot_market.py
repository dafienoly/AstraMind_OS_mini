"""Exact-version DuckDB reader for research and backtests."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import cast

import duckdb

from ..domain.backtest_models import ResearchBar, UniverseRules


class SnapshotMarketReader:
    def __init__(self, data_root: Path, snapshot_id: str) -> None:
        self._root = data_root
        digest = snapshot_id.rsplit(":", 1)[-1]
        snapshot_path = data_root / "snapshots" / digest / "manifest.json"
        if not snapshot_path.is_file():
            raise FileNotFoundError(f"快照不存在：{snapshot_id}")
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if snapshot.get("snapshot_id") != snapshot_id:
            raise ValueError("快照身份与路径不一致")
        self._manifests = {
            item["dataset_name"]: self._load_manifest(
                str(item["dataset_name"]), str(item["dataset_version"])
            )
            for item in snapshot["datasets"]
        }

    def eligible_instruments(
        self,
        *,
        as_of: date,
        rules: UniverseRules,
        limit: int = 30,
    ) -> tuple[str, ...]:
        paths = self._paths
        with duckdb.connect(":memory:") as connection:
            self._event_views(connection)
            rows = connection.execute(
                """
                WITH listed AS (
                  SELECT instrument_id, trade_date, risk_status, buy_state, sell_state,
                         row_number() OVER (
                           PARTITION BY instrument_id ORDER BY trade_date
                         ) AS listed_sessions
                  FROM read_parquet(?) WHERE trade_date <= ?
                ), state AS (
                  SELECT * FROM listed
                  QUALIFY row_number() OVER (
                    PARTITION BY instrument_id ORDER BY trade_date DESC
                  ) = 1
                ), amounts AS (
                  SELECT instrument_id, median(amount_thousand_cny) * 1000 AS amount_20d
                  FROM (
                    SELECT instrument_id, amount_thousand_cny,
                           row_number() OVER (
                             PARTITION BY instrument_id ORDER BY trade_date DESC
                           ) AS recent
                    FROM read_parquet(?) WHERE trade_date <= ?
                  ) WHERE recent <= 20 GROUP BY instrument_id
                )
                SELECT s.instrument_id
                FROM state s JOIN amounts a USING (instrument_id)
                WHERE s.trade_date = ?
                  AND s.listed_sessions >= ?
                  AND s.risk_status = 'normal'
                  AND s.buy_state = 'tradable' AND s.sell_state = 'tradable'
                  AND a.amount_20d >= ?
                ORDER BY a.amount_20d DESC, s.instrument_id
                LIMIT ?
                """,
                [
                    paths("daily_tradability"),
                    as_of,
                    paths("daily_market"),
                    as_of,
                    as_of,
                    rules.minimum_listed_sessions,
                    rules.minimum_median_amount_20d_cny,
                    limit,
                ],
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def load_bars(
        self,
        *,
        instruments: tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> tuple[ResearchBar, ...]:
        if not instruments:
            return ()
        paths = self._paths
        with duckdb.connect(":memory:") as connection:
            rows = connection.execute(
                """
                WITH states AS (
                  SELECT instrument_id, trade_date, risk_status, buy_state, sell_state,
                         has_daily_bar, upper_limit_locked, lower_limit_locked,
                         row_number() OVER (
                           PARTITION BY instrument_id ORDER BY trade_date
                         ) AS listed_sessions
                  FROM read_parquet(?)
                  WHERE instrument_id IN (SELECT unnest(?)) AND trade_date <= ?
                )
                SELECT d.instrument_id, d.trade_date, d.open, d.high, d.low, d.close,
                       a.research_close_index,
                       d.amount_thousand_cny * 1000 AS amount_cny,
                       b.turnover_rate, s.listed_sessions, s.risk_status,
                       s.buy_state, s.sell_state, s.has_daily_bar,
                       s.upper_limit_locked, s.lower_limit_locked,
                       coalesce(e.event_count, 0), e.net_rate,
                       e.institutional_net_buy_cny, h.holder_change_rate
                FROM read_parquet(?) d
                JOIN read_parquet(?) a USING (instrument_id, trade_date)
                JOIN states s USING (instrument_id, trade_date)
                LEFT JOIN read_parquet(?) b USING (instrument_id, trade_date)
                LEFT JOIN lhb_context e USING (instrument_id, trade_date)
                LEFT JOIN LATERAL (
                  SELECT holder_change_rate FROM shareholder_context x
                  WHERE x.instrument_id = d.instrument_id
                    AND x.available_at <= timezone(
                      'Asia/Shanghai',
                      CAST(d.trade_date AS TIMESTAMP) + INTERVAL '18 hours'
                    )
                  ORDER BY x.available_at DESC, x.reporting_period DESC
                  LIMIT 1
                ) h ON true
                WHERE d.instrument_id IN (SELECT unnest(?))
                  AND d.trade_date BETWEEN ? AND ?
                ORDER BY d.trade_date, d.instrument_id
                """,
                [
                    paths("daily_tradability"),
                    list(instruments),
                    end_date,
                    paths("daily_market"),
                    paths("adjusted_market"),
                    paths("daily_basic"),
                    list(instruments),
                    start_date,
                    end_date,
                ],
            ).fetchall()
        return tuple(ResearchBar(*row) for row in rows)

    def _event_views(self, connection: duckdb.DuckDBPyConnection) -> None:
        event_paths = self._optional_paths("lhb_event")
        seat_paths = self._optional_paths("lhb_seat")
        holder_paths = self._optional_paths("shareholder_count")
        if event_paths:
            connection.execute(
                """
                CREATE TEMP TABLE lhb_event_source AS
                SELECT * FROM read_parquet(?)
                """,
                [event_paths],
            )
        else:
            connection.execute(
                """
                CREATE TEMP TABLE lhb_event_source (
                  instrument_id VARCHAR, trade_date DATE, net_rate DOUBLE
                )
                """
            )
        if seat_paths:
            connection.execute(
                """
                CREATE TEMP TABLE lhb_seat_source AS
                SELECT * FROM read_parquet(?)
                """,
                [seat_paths],
            )
        else:
            connection.execute(
                """
                CREATE TEMP TABLE lhb_seat_source (
                  instrument_id VARCHAR, trade_date DATE, net_buy_cny DOUBLE
                )
                """
            )
        connection.execute(
            """
            CREATE TEMP VIEW lhb_context AS
            WITH events AS (
              SELECT instrument_id, trade_date, count(*) AS event_count,
                     sum(net_rate) AS net_rate
              FROM lhb_event_source GROUP BY instrument_id, trade_date
            ), seats AS (
              SELECT instrument_id, trade_date, sum(net_buy_cny) AS institutional_net_buy_cny
              FROM lhb_seat_source GROUP BY instrument_id, trade_date
            )
            SELECT e.*, s.institutional_net_buy_cny
            FROM events e LEFT JOIN seats s USING (instrument_id, trade_date)
            """
        )
        if holder_paths:
            connection.execute(
                """
                CREATE TEMP TABLE shareholder_source AS
                SELECT * FROM read_parquet(?)
                """,
                [holder_paths],
            )
            connection.execute(
                """
                CREATE TEMP VIEW shareholder_context AS
                SELECT instrument_id, reporting_period, available_at,
                       holder_count / nullif(lag(holder_count) OVER (
                         PARTITION BY instrument_id
                         ORDER BY available_at, reporting_period
                       ), 0) - 1 AS holder_change_rate
                FROM shareholder_source
                """
            )
        else:
            connection.execute(
                """
                CREATE TEMP VIEW shareholder_context AS
                SELECT NULL::VARCHAR instrument_id, NULL::DATE reporting_period,
                       NULL::TIMESTAMPTZ available_at, NULL::DOUBLE holder_change_rate
                WHERE false
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
        return manifest

    def _paths(self, name: str) -> list[str]:
        manifest = self._manifests.get(name)
        if manifest is None:
            raise ValueError(f"快照缺少研究数据集：{name}")
        version = str(manifest["dataset_version"]).rsplit(":", 1)[-1]
        base = self._root / "datasets" / name / version
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
        if name not in self._manifests:
            return []
        return self._paths(name)


__all__ = ["SnapshotMarketReader"]
