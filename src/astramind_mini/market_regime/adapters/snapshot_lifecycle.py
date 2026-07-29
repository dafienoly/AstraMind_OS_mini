"""Build the lifecycle map from one exact immutable DataSnapshot."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import date, datetime, time
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..contracts.lifecycle import (
    IndustryLifecycleIntradayPoint,
    IndustryLifecycleIntradayProjection,
    IndustryLifecycleProjection,
)
from ..domain.lifecycle import (
    METHOD_VERSION,
    IndustryIdentity,
    MembershipInterval,
    PriceObservation,
    StockStructure,
    build_industry_points,
    compute_stock_structures,
)
from ..domain.lifecycle_intraday import (
    PreparedStock,
    compute_intraday_structures,
    prepare_intraday_stocks,
)

REQUIRED_DATASETS = (
    "adjusted_market",
    "daily_market",
    "industry_membership",
    "industry_taxonomy",
    "trade_calendar",
)


class SnapshotIndustryLifecycle:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root
        self._intraday_cutoff: date | None = None
        self._prepared_stocks: dict[str, PreparedStock] = {}
        self._intraday_scales: dict[str, float] = {}
        self._intraday_historical: dict[date, dict[str, StockStructure]] = {}
        self._intraday_identities: tuple[IndustryIdentity, ...] = ()
        self._intraday_memberships: tuple[MembershipInterval, ...] = ()
        self._intraday_amount_shares: dict[str, float] = {}

    def current(self) -> IndustryLifecycleProjection:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        if not isinstance(pointer, dict) or not isinstance(pointer.get("snapshot_id"), str):
            raise ValueError("当前数据快照指针无效")
        return self.load(pointer["snapshot_id"])

    def load(self, snapshot_id: str) -> IndustryLifecycleProjection:
        return _cached_projection(str(self._root.resolve()), snapshot_id)

    def intraday(
        self,
        *,
        prices: Mapping[str, float],
        market_date: date,
        session_id: str,
        state: str,
        as_of: datetime,
    ) -> IndustryLifecycleIntradayProjection:
        completed = self.current()
        if completed.evidence_cutoff is None or market_date <= completed.evidence_cutoff:
            return _blocked_intraday(completed, session_id, state, as_of, "no_new_intraday_session")
        snapshot = self._snapshot(completed.data_snapshot_id)
        references = {item.dataset_name: item for item in snapshot.datasets}
        if any(name not in references for name in REQUIRED_DATASETS):
            return _blocked_intraday(completed, session_id, state, as_of, "snapshot_inputs_missing")
        paths = {
            name: self._paths(name, references[name].dataset_version, references[name].content_hash)
            for name in REQUIRED_DATASETS
        }
        with duckdb.connect(":memory:") as connection:
            sessions = self._sessions(
                connection,
                paths["adjusted_market"],
                completed.evidence_cutoff,
                279,
            )
            if len(sessions) < 252:
                return _blocked_intraday(
                    completed, session_id, state, as_of, "insufficient_market_history"
                )
            self._prepare_intraday(
                connection,
                paths=paths,
                sessions=sessions,
                cutoff=completed.evidence_cutoff,
            )
            evaluation_dates = (*sessions[-24:], market_date)
            current_prices = {
                instrument_id: price * scale
                for instrument_id, price in prices.items()
                if (scale := self._intraday_scales.get(instrument_id)) is not None
            }
            structures = dict(self._intraday_historical)
            structures[market_date] = compute_intraday_structures(
                self._prepared_stocks,
                current_prices,
                market_date,
            )
        points = build_industry_points(
            identities=self._intraday_identities,
            memberships=self._intraday_memberships,
            evaluation_dates=evaluation_dates,
            structures=structures,
            amount_shares=self._intraday_amount_shares,
        )
        available = tuple(
            IndustryLifecycleIntradayPoint(
                industry_code=point.industry_code,
                strong_participation=point.strong_participation,
                low_participation=point.low_participation,
                valid_member_count=point.valid_member_count,
                coverage_ratio=point.coverage_ratio,
            )
            for point in points
            if point.strong_participation is not None and point.low_participation is not None
        )
        return IndustryLifecycleIntradayProjection(
            provider="miniqmt",
            session_id=session_id,
            state=state,  # type: ignore[arg-type]
            as_of=as_of,
            anchor_date=completed.evidence_cutoff,
            points=available,
            known_gaps=() if available else ("all_industries_below_intraday_coverage",),
        )

    def _build(self, snapshot_id: str) -> IndustryLifecycleProjection:
        snapshot = self._snapshot(snapshot_id)
        references = {item.dataset_name: item for item in snapshot.datasets}
        missing = tuple(name for name in REQUIRED_DATASETS if name not in references)
        if missing:
            return IndustryLifecycleProjection(
                status="blocked",
                data_snapshot_id=snapshot.snapshot_id,
                as_of=snapshot.as_of,
                method_version=METHOD_VERSION,
                known_gaps=tuple(f"missing_dataset:{name}" for name in missing),
            )
        paths = {
            name: self._paths(name, references[name].dataset_version, references[name].content_hash)
            for name in REQUIRED_DATASETS
        }
        with duckdb.connect(":memory:") as connection:
            cutoff = self._cutoff(connection, paths)
            sessions = self._sessions(connection, paths["adjusted_market"], cutoff, 280)
            if len(sessions) < 252:
                return IndustryLifecycleProjection(
                    status="blocked",
                    data_snapshot_id=snapshot.snapshot_id,
                    as_of=snapshot.as_of,
                    evidence_cutoff=cutoff,
                    method_version=METHOD_VERSION,
                    known_gaps=("insufficient_market_history",),
                )
            evaluation_dates = sessions[-25:]
            identities, taxonomy_version = self._identities(connection, paths["industry_taxonomy"])
            memberships = self._memberships(connection, paths["industry_membership"])
            structures = compute_stock_structures(
                self._prices(
                    connection,
                    adjusted=_from_year(paths["adjusted_market"], sessions[0].year),
                    membership=paths["industry_membership"],
                    start=sessions[0],
                    cutoff=cutoff,
                ),
                evaluation_dates,
                sessions=sessions,
            )
            amount_shares = self._amount_shares(
                connection,
                market=paths["daily_market"],
                membership=paths["industry_membership"],
                evaluation_dates=evaluation_dates[-20:],
            )
        industries = build_industry_points(
            identities=identities,
            memberships=memberships,
            evaluation_dates=evaluation_dates,
            structures=structures,
            amount_shares=amount_shares,
        )
        gaps: list[str] = []
        if not identities:
            gaps.append("industry_registry_missing")
        if all(item.strong_participation is None for item in industries):
            gaps.append("all_industries_below_coverage")
        expected_cutoff = self._expected_cutoff(paths["trade_calendar"], snapshot.as_of)
        stale = cutoff < expected_cutoff
        if stale:
            gaps.append("snapshot_cutoff_before_as_of_date")
        return IndustryLifecycleProjection(
            status="blocked" if not identities else "stale" if stale else "ready",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of,
            evidence_cutoff=cutoff,
            taxonomy_version=taxonomy_version,
            method_version=METHOD_VERSION,
            industries=industries,
            known_gaps=tuple(gaps),
        )

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = _digest(snapshot_id, "snapshot:sha256")
        snapshot = DataSnapshot.model_validate_json(
            (self._root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
        )
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("生命周期快照身份与路径不一致")
        return snapshot

    def _paths(self, name: str, version: str, content_hash: str) -> tuple[Path, ...]:
        digest = _digest(version, "sha256")
        directory = self._root / "datasets" / name / digest
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest.get("dataset_version") != version
            or manifest.get("content_hash") != content_hash
        ):
            raise ValueError(f"生命周期数据集身份冲突：{name}")
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"生命周期数据集制品无效：{name}")
        paths = tuple(directory / str(item) for item in artifacts if str(item).endswith(".parquet"))
        if not paths or any(not item.is_file() for item in paths):
            raise ValueError(f"生命周期数据集制品缺失：{name}")
        return paths

    @staticmethod
    def _cutoff(
        connection: duckdb.DuckDBPyConnection,
        paths: dict[str, tuple[Path, ...]],
    ) -> date:
        row = connection.execute(
            """
            SELECT least(
              (SELECT max(trade_date) FROM read_parquet(?)),
              (SELECT max(trade_date) FROM read_parquet(?))
            )
            """,
            [_strings(paths["adjusted_market"]), _strings(paths["daily_market"])],
        ).fetchone()
        if row is None or not isinstance(row[0], date):
            raise ValueError("生命周期没有共同证据截止日")
        return row[0]

    @staticmethod
    def _sessions(
        connection: duckdb.DuckDBPyConnection,
        adjusted: tuple[Path, ...],
        cutoff: date,
        limit: int,
    ) -> tuple[date, ...]:
        rows = connection.execute(
            """
            SELECT trade_date FROM (
              SELECT DISTINCT trade_date FROM read_parquet(?) WHERE trade_date <= ?
              ORDER BY trade_date DESC LIMIT ?
            ) ORDER BY trade_date
            """,
            [_strings(adjusted), cutoff, limit],
        ).fetchall()
        return tuple(item[0] for item in rows if isinstance(item[0], date))

    @staticmethod
    def _identities(
        connection: duckdb.DuckDBPyConnection,
        taxonomy: tuple[Path, ...],
    ) -> tuple[tuple[IndustryIdentity, ...], str]:
        rows = connection.execute(
            """
            SELECT industry_code, industry_name, taxonomy_version
            FROM read_parquet(?)
            WHERE taxonomy = 'SW' AND level = 'L1' AND is_published
            ORDER BY industry_code
            """,
            [_strings(taxonomy)],
        ).fetchall()
        versions = {str(item[2]) for item in rows}
        if len(versions) != 1:
            raise ValueError("生命周期行业分类版本不唯一")
        return (
            tuple(IndustryIdentity(str(item[0]), str(item[1])) for item in rows),
            versions.pop(),
        )

    @staticmethod
    def _memberships(
        connection: duckdb.DuckDBPyConnection,
        membership: tuple[Path, ...],
    ) -> tuple[MembershipInterval, ...]:
        rows = connection.execute(
            """
            SELECT instrument_id, industry_code, effective_from, effective_to
            FROM read_parquet(?) WHERE taxonomy = 'SW' AND level = 'L1'
            """,
            [_strings(membership)],
        ).fetchall()
        return tuple(MembershipInterval(str(row[0]), str(row[1]), row[2], row[3]) for row in rows)

    @staticmethod
    def _prices(
        connection: duckdb.DuckDBPyConnection,
        *,
        adjusted: tuple[Path, ...],
        membership: tuple[Path, ...],
        start: date,
        cutoff: date,
    ) -> Iterator[PriceObservation]:
        cursor = connection.execute(
            """
            SELECT instrument_id, trade_date, research_close_index
            FROM read_parquet(?)
            WHERE trade_date BETWEEN ? AND ?
              AND research_close_index > 0
              AND instrument_id IN (
                SELECT DISTINCT instrument_id FROM read_parquet(?)
                WHERE taxonomy = 'SW' AND level = 'L1'
              )
            ORDER BY instrument_id, trade_date
            """,
            [_strings(adjusted), start, cutoff, _strings(membership)],
        )
        while rows := cursor.fetchmany(10_000):
            for row in rows:
                yield PriceObservation(str(row[0]), row[1], float(row[2]))

    @staticmethod
    def _amount_shares(
        connection: duckdb.DuckDBPyConnection,
        *,
        market: tuple[Path, ...],
        membership: tuple[Path, ...],
        evaluation_dates: tuple[date, ...],
    ) -> dict[str, float]:
        rows = connection.execute(
            """
            WITH selected AS (
              SELECT instrument_id, trade_date, amount_thousand_cny
              FROM read_parquet(?) WHERE trade_date IN (SELECT unnest(?::DATE[]))
            ), assigned AS (
              SELECT m.industry_code, d.amount_thousand_cny
              FROM selected d JOIN read_parquet(?) m
                ON d.instrument_id = m.instrument_id
               AND m.taxonomy = 'SW' AND m.level = 'L1'
               AND m.effective_from <= d.trade_date
               AND (m.effective_to IS NULL OR d.trade_date < m.effective_to)
            ), totals AS (
              SELECT industry_code, sum(amount_thousand_cny) AS amount FROM assigned
              GROUP BY industry_code
            )
            SELECT industry_code, amount / sum(amount) OVER () FROM totals
            """,
            [_strings(market), list(evaluation_dates), _strings(membership)],
        ).fetchall()
        return {str(row[0]): float(row[1]) for row in rows if row[1] is not None}

    def _prepare_intraday(
        self,
        connection: duckdb.DuckDBPyConnection,
        *,
        paths: dict[str, tuple[Path, ...]],
        sessions: tuple[date, ...],
        cutoff: date,
    ) -> None:
        if self._intraday_cutoff == cutoff:
            return
        observations = tuple(
            self._prices(
                connection,
                adjusted=_from_year(paths["adjusted_market"], sessions[0].year),
                membership=paths["industry_membership"],
                start=sessions[0],
                cutoff=cutoff,
            )
        )
        self._prepared_stocks = prepare_intraday_stocks(observations, sessions)
        self._intraday_historical = compute_stock_structures(
            observations,
            sessions[-24:],
            sessions=sessions,
        )
        rows = connection.execute(
            """
            SELECT instrument_id, raw_close, research_close_index
            FROM read_parquet(?) WHERE trade_date = ?
            """,
            [_strings(paths["adjusted_market"]), cutoff],
        ).fetchall()
        self._intraday_scales = {
            str(instrument_id): float(research_close) / float(raw_close)
            for instrument_id, raw_close, research_close in rows
            if raw_close and research_close
        }
        self._intraday_identities, _ = self._identities(connection, paths["industry_taxonomy"])
        self._intraday_memberships = self._memberships(connection, paths["industry_membership"])
        self._intraday_amount_shares = self._amount_shares(
            connection,
            market=paths["daily_market"],
            membership=paths["industry_membership"],
            evaluation_dates=sessions[-20:],
        )
        self._intraday_cutoff = cutoff

    def _expected_cutoff(self, paths: tuple[Path, ...], as_of: object) -> date:
        if not hasattr(as_of, "astimezone"):
            raise ValueError("生命周期快照时间无效")
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
                [_strings(paths), upper],
            ).fetchone()
        if row is None or not isinstance(row[0], date):
            raise ValueError("生命周期无法解析预期完成交易日")
        return row[0]


def _strings(paths: tuple[Path, ...]) -> list[str]:
    return [str(item) for item in paths]


def _blocked_intraday(
    completed: IndustryLifecycleProjection,
    session_id: str,
    state: str,
    as_of: datetime,
    gap: str,
) -> IndustryLifecycleIntradayProjection:
    if completed.evidence_cutoff is None:
        raise ValueError("生命周期完成日锚点缺失")
    return IndustryLifecycleIntradayProjection(
        provider="miniqmt",
        session_id=session_id,
        state="blocked" if state != "disconnected" else "disconnected",
        as_of=as_of,
        anchor_date=completed.evidence_cutoff,
        known_gaps=(gap,),
    )


def _from_year(paths: tuple[Path, ...], first_year: int) -> tuple[Path, ...]:
    selected = tuple(item for item in paths if _artifact_year(item) >= first_year)
    return selected or paths


def _artifact_year(path: Path) -> int:
    try:
        return int(path.stem.rsplit("-", 1)[-1])
    except ValueError:
        return 0


def _digest(identity: str, prefix: str) -> str:
    value = identity.removeprefix(prefix + ":")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


__all__ = ["SnapshotIndustryLifecycle"]


@lru_cache(maxsize=4)
def _cached_projection(data_root: str, snapshot_id: str) -> IndustryLifecycleProjection:
    return SnapshotIndustryLifecycle(Path(data_root))._build(snapshot_id)
