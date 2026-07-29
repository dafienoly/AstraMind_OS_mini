"""Read one exact DataSnapshot for L1→L2→stock research slices."""

from __future__ import annotations

from datetime import date, datetime, time
from pathlib import Path
from typing import Literal

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..application.rotation import production_formula
from ..contracts import IndustryHierarchyNode, IndustryHierarchyView, MarketRotationSnapshot
from ..domain.rotation import build_rotation_snapshot
from .hierarchy_queries import (
    close_series,
    has_l2,
    member_nodes,
    snapshot_at,
    snapshot_paths,
    taxonomy_nodes,
)
from .stock_evidence_queries import price_candles, stock_evidence

REQUIRED_DATASETS = {
    "daily_market",
    "industry_index_daily",
    "industry_membership",
    "industry_taxonomy",
    "security_master",
    "trade_calendar",
}


class SnapshotIndustryHierarchy:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def load(
        self,
        *,
        data_snapshot_id: str,
        as_of: date,
        parent_code: str | None = None,
        l2_code: str | None = None,
        instrument_id: str | None = None,
        all_l2: bool = False,
    ) -> IndustryHierarchyView:
        snapshot = snapshot_at(self._root, data_snapshot_id)
        if as_of > snapshot.as_of.date():
            return self._blocked(snapshot, as_of, parent_code, "requested_date_after_snapshot")
        paths = snapshot_paths(self._root, snapshot)
        if missing := sorted(REQUIRED_DATASETS - paths.keys()):
            return self._blocked(
                snapshot, as_of, parent_code, f"missing_datasets:{','.join(missing)}"
            )
        with duckdb.connect(":memory:") as connection:
            if not has_l2(connection, paths["industry_taxonomy"]):
                return self._blocked(snapshot, as_of, parent_code, "sw2021_l2_not_published")
            if l2_code:
                try:
                    return self._stocks(
                        connection,
                        snapshot,
                        paths,
                        as_of,
                        parent_code,
                        l2_code,
                        instrument_id,
                    )
                except ValueError:
                    return self._blocked(
                        snapshot,
                        as_of,
                        parent_code,
                        "same_level_history_incomplete",
                        level="stock",
                    )
            if parent_code:
                try:
                    return self._l2(connection, snapshot, paths, as_of, parent_code, all_l2)
                except ValueError:
                    return self._blocked(
                        snapshot, as_of, parent_code, "same_level_history_incomplete"
                    )
            return self._l1(connection, snapshot, paths, as_of)

    def _l1(
        self,
        connection: duckdb.DuckDBPyConnection,
        snapshot: DataSnapshot,
        paths: dict[str, list[str]],
        as_of: date,
    ) -> IndustryHierarchyView:
        return IndustryHierarchyView(
            status="ready",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=as_of,
            level="L1",
            comparison_scope="l1",
            benchmark_id="SW2021:L1:equal_weight_index_return",
            nodes=taxonomy_nodes(
                connection, paths["industry_taxonomy"], level="L1", parent_code=None
            ),
        )

    def _l2(
        self,
        connection: duckdb.DuckDBPyConnection,
        snapshot: DataSnapshot,
        paths: dict[str, list[str]],
        as_of: date,
        parent_code: str,
        all_l2: bool,
    ) -> IndustryHierarchyView:
        nodes = taxonomy_nodes(
            connection,
            paths["industry_taxonomy"],
            level="L2",
            parent_code=None if all_l2 else parent_code,
        )
        benchmark = (
            "SW2021:L2:all_equal_weight_index_return"
            if all_l2
            else f"SW2021:L2:{parent_code}:sibling_equal_weight_index_return"
        )
        if len(nodes) < 3:
            return IndustryHierarchyView(
                status="ready",
                data_snapshot_id=snapshot.snapshot_id,
                as_of=as_of,
                level="L2",
                comparison_scope="all_l2" if all_l2 else "siblings",
                benchmark_id=benchmark,
                parent_code=parent_code,
                nodes=nodes,
                known_gaps=(
                    "sibling_cross_section_below_three",
                    "sw2021_pre2021_provider_backcast",
                ),
            )
        rotation, _ = self._rotation(
            connection,
            snapshot,
            paths["industry_index_daily"],
            nodes,
            as_of,
            benchmark,
            paths["trade_calendar"],
        )
        return IndustryHierarchyView(
            status="ready",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=as_of,
            level="L2",
            comparison_scope="all_l2" if all_l2 else "siblings",
            benchmark_id=benchmark,
            parent_code=parent_code,
            nodes=nodes,
            rotation=rotation,
            known_gaps=("sw2021_pre2021_provider_backcast",),
        )

    def _stocks(
        self,
        connection: duckdb.DuckDBPyConnection,
        snapshot: DataSnapshot,
        paths: dict[str, list[str]],
        as_of: date,
        parent_code: str | None,
        l2_code: str,
        instrument_id: str | None,
    ) -> IndustryHierarchyView:
        nodes = member_nodes(
            connection,
            paths["industry_membership"],
            paths["security_master"],
            l2_code=l2_code,
            as_of=as_of,
        )
        benchmark = f"SW2021:L2:{l2_code}:member_equal_weight_return"
        valid_codes = {node.code for node in nodes}
        if instrument_id is not None and instrument_id not in valid_codes:
            raise ValueError("所选股票不属于指定日期的二级行业")
        selected = instrument_id or (nodes[0].code if nodes else None)
        rotation, excluded = self._rotation(
            connection,
            snapshot,
            paths["daily_market"],
            nodes,
            as_of,
            benchmark,
            paths["trade_calendar"],
            stock=True,
        )
        gaps = ["research_ranking_not_investment_advice"]
        if excluded:
            gaps.append(
                f"stock_rotation_incomplete_panel_excluded:{len(excluded)}:{','.join(excluded)}"
            )
        return IndustryHierarchyView(
            status="ready",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=as_of,
            level="stock",
            comparison_scope="members",
            benchmark_id=benchmark,
            parent_code=parent_code,
            selected_code=selected,
            nodes=nodes,
            rotation=rotation,
            candles=price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=as_of,
                period="day",
            ),
            weekly_candles=price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=as_of,
                period="week",
            ),
            monthly_candles=price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=as_of,
                period="month",
            ),
            stock_evidence=(
                stock_evidence(
                    connection,
                    paths,
                    instrument_id=selected,
                    instrument_name=next(node.name for node in nodes if node.code == selected),
                    as_of=as_of,
                )
                if selected is not None
                else None
            ),
            known_gaps=tuple(gaps),
        )

    def _rotation(
        self,
        connection: duckdb.DuckDBPyConnection,
        snapshot: DataSnapshot,
        paths: list[str],
        nodes: tuple[IndustryHierarchyNode, ...],
        as_of: date,
        benchmark: str,
        calendar_paths: list[str],
        *,
        stock: bool = False,
    ) -> tuple[MarketRotationSnapshot, tuple[str, ...]]:
        calendar, series, excluded = close_series(
            connection,
            paths,
            nodes,
            as_of=as_of,
            stock=stock,
            allow_incomplete=stock,
            calendar_paths=calendar_paths,
        )
        formula = production_formula().model_copy(
            update={
                "benchmark_id": benchmark,
                "benchmark_definition_version": "wp-0026-v1.0.0",
                "minimum_constituent_count": 1 if stock else 3,
            }
        )
        gaps = (f"stock_rotation_incomplete_panel_excluded:{len(excluded)}",) if excluded else ()
        return build_rotation_snapshot(
            data_snapshot_id=snapshot.snapshot_id,
            as_of=datetime.combine(as_of, time(18), tzinfo=snapshot.as_of.tzinfo),
            created_at=snapshot.created_at,
            calendar=calendar,
            industries=series,
            formula=formula,
            known_gaps=gaps,
        ), excluded

    def _blocked(
        self,
        snapshot: DataSnapshot,
        as_of: date,
        parent_code: str | None,
        reason: str,
        *,
        level: Literal["L1", "L2", "stock"] | None = None,
    ) -> IndustryHierarchyView:
        resolved_level = level or ("L2" if parent_code else "L1")
        return IndustryHierarchyView(
            status="blocked",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=as_of,
            level=resolved_level,
            comparison_scope=(
                "members" if resolved_level == "stock" else "siblings" if parent_code else "l1"
            ),
            benchmark_id="SW2021:hierarchy:unavailable",
            parent_code=parent_code,
            known_gaps=(reason,),
        )


__all__ = ["SnapshotIndustryHierarchy"]
