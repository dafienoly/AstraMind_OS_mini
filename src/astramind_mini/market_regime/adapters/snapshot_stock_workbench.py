"""Build the canonical stock workbench from one immutable DataSnapshot."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.contracts import DataSnapshot

from ..contracts.stock_workbench import (
    CompletedStockMarketEvidence,
    EvidenceSectionIdentity,
    StockIndustryContext,
    StockInspectionFocus,
    StockInspectionMode,
    StockInspectionOrigin,
    StockInstrumentIdentity,
    StockReturnTarget,
    StockWorkbenchProjection,
)
from ..domain.identity import content_hash
from .hierarchy_queries import snapshot_at, snapshot_paths
from .stock_evidence_queries import price_candles, stock_evidence

REQUIRED_DATASETS = {
    "daily_market",
    "industry_membership",
    "security_master",
    "security_name_history",
    "trade_calendar",
}


class SnapshotStockWorkbench:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(
        self,
        instrument_id: str,
        *,
        origin: StockInspectionOrigin,
        mode: StockInspectionMode,
        return_target: StockReturnTarget,
        industry_code: str | None = None,
    ) -> StockWorkbenchProjection:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        return self.load(
            instrument_id,
            data_snapshot_id=str(pointer["snapshot_id"]),
            as_of=None,
            origin=origin,
            mode=mode,
            return_target=return_target,
            industry_code=industry_code,
        )

    def load(
        self,
        instrument_id: str,
        *,
        data_snapshot_id: str,
        as_of: date | None,
        origin: StockInspectionOrigin,
        mode: StockInspectionMode,
        return_target: StockReturnTarget,
        industry_code: str | None = None,
    ) -> StockWorkbenchProjection:
        snapshot = snapshot_at(self._root, data_snapshot_id)
        cutoff = min(as_of or snapshot.as_of.date(), snapshot.as_of.date())
        paths = snapshot_paths(self._root, snapshot)
        missing = sorted(REQUIRED_DATASETS - paths.keys())
        if missing:
            raise ValueError(f"stock_workbench_missing_datasets:{','.join(missing)}")
        providers = self._providers(snapshot)
        now = datetime.now(UTC)
        with duckdb.connect(":memory:") as connection:
            identity = _instrument_identity(connection, paths, instrument_id, cutoff)
            industry = _industry_context(
                connection,
                paths,
                providers,
                instrument_id,
                cutoff,
            )
            daily = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=instrument_id,
                as_of=cutoff,
                period="day",
            )
            weekly = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=instrument_id,
                as_of=cutoff,
                period="week",
            )
            monthly = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=instrument_id,
                as_of=cutoff,
                period="month",
            )
            evidence = stock_evidence(
                connection,
                paths,
                instrument_id=instrument_id,
                instrument_name=identity.instrument_name,
                as_of=cutoff,
            )
        focus_value = {
            "instrument_id": instrument_id,
            "origin": origin,
            "as_of": cutoff,
            "data_snapshot_id": snapshot.snapshot_id,
            "industry_code": industry_code,
            "mode": mode,
            "return_target": return_target,
        }
        focus = StockInspectionFocus(
            focus_id=content_hash(focus_value),
            instrument_id=instrument_id,
            origin=origin,
            as_of=cutoff,
            data_snapshot_id=snapshot.snapshot_id,
            industry_code=industry_code,
            mode=mode,
            return_target=return_target,
            created_at=now,
        )
        market_identity = content_hash(
            {
                "snapshot": snapshot.snapshot_id,
                "instrument": instrument_id,
                "cutoff": cutoff,
                "daily": [item.model_dump(mode="json") for item in daily],
                "weekly": [item.model_dump(mode="json") for item in weekly],
                "monthly": [item.model_dump(mode="json") for item in monthly],
            }
        )
        completed = CompletedStockMarketEvidence(
            evidence=EvidenceSectionIdentity(
                state="ready" if daily else "unavailable",
                as_of=cutoff,
                provider=providers.get("daily_market", "unknown"),
                content_identity=market_identity,
                known_gaps=() if daily else ("daily_market_instrument_unavailable",),
            ),
            daily=daily,
            weekly=weekly,
            monthly=monthly,
        )
        projection_identity = content_hash(
            {
                "focus": focus.model_dump(mode="json"),
                "instrument": identity.model_dump(mode="json"),
                "market": market_identity,
                "industry": industry.model_dump(mode="json"),
                "stock_evidence": evidence.model_dump(mode="json"),
            }
        )
        return StockWorkbenchProjection(
            focus=focus,
            instrument_identity=identity,
            completed_market_evidence=completed,
            industry_context=industry,
            stock_evidence=evidence,
            content_identity=projection_identity,
            known_gaps=tuple(sorted(set(evidence.known_gaps + industry.evidence.known_gaps))),
        )

    def _providers(self, snapshot: DataSnapshot) -> dict[str, str]:
        providers: dict[str, str] = {}
        for reference in snapshot.datasets:
            digest = reference.dataset_version.removeprefix("sha256:")
            manifest = json.loads(
                (
                    self._root / "datasets" / reference.dataset_name / digest / "manifest.json"
                ).read_text(encoding="utf-8")
            )
            providers[reference.dataset_name] = str(manifest.get("provider", "unknown"))
        return providers


def _instrument_identity(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
    instrument_id: str,
    as_of: date,
) -> StockInstrumentIdentity:
    row = connection.execute(
        """
        SELECT s.instrument_id,
               coalesce(n.name, s.name) AS instrument_name,
               s.exchange,
               s.market,
               n.risk_status,
               n.is_special_treatment
        FROM read_parquet(?) s
        LEFT JOIN read_parquet(?) n
          ON s.instrument_id = n.instrument_id
         AND n.effective_start_date <= ?
         AND (n.effective_end_date IS NULL OR ? <= n.effective_end_date)
         AND CAST(n.available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
        WHERE s.instrument_id = ?
        ORDER BY n.effective_start_date DESC NULLS LAST
        LIMIT 1
        """,
        [
            paths["security_master"],
            paths["security_name_history"],
            as_of,
            as_of,
            as_of,
            instrument_id,
        ],
    ).fetchone()
    if row is None:
        raise FileNotFoundError(instrument_id)
    return StockInstrumentIdentity(
        instrument_id=str(row[0]),
        instrument_name=str(row[1]),
        exchange=str(row[2] or ""),
        market=str(row[3] or ""),
        risk_status=str(row[4]) if row[4] is not None else None,
        is_special_treatment=bool(row[5]) if row[5] is not None else None,
    )


def _industry_context(
    connection: duckdb.DuckDBPyConnection,
    paths: dict[str, list[str]],
    providers: dict[str, str],
    instrument_id: str,
    as_of: date,
) -> StockIndustryContext:
    rows = connection.execute(
        """
        SELECT level, industry_code, industry_name, taxonomy_version
        FROM read_parquet(?)
        WHERE instrument_id = ?
          AND level IN ('L1', 'L2')
          AND effective_from <= ?
          AND (effective_to IS NULL OR ? < effective_to)
          AND CAST(available_at AT TIME ZONE 'Asia/Shanghai' AS DATE) <= ?
        ORDER BY level
        """,
        [paths["industry_membership"], instrument_id, as_of, as_of, as_of],
    ).fetchall()
    values = {
        str(level): (str(code), str(name), str(version)) for level, code, name, version in rows
    }
    l1 = values.get("L1")
    l2 = values.get("L2")
    gaps = () if l1 and l2 else ("point_in_time_industry_membership_incomplete",)
    payload = {"instrument_id": instrument_id, "as_of": as_of, "l1": l1, "l2": l2}
    return StockIndustryContext(
        evidence=EvidenceSectionIdentity(
            state="ready" if l1 or l2 else "unavailable",
            as_of=as_of,
            provider=providers.get("industry_membership", "unknown"),
            content_identity=content_hash(payload),
            known_gaps=gaps,
        ),
        taxonomy="SW",
        taxonomy_version=(l2 or l1 or ("", "", "SW2021"))[2],
        l1_code=l1[0] if l1 else None,
        l1_name=l1[1] if l1 else None,
        l2_code=l2[0] if l2 else None,
        l2_name=l2[1] if l2 else None,
    )


__all__ = ["SnapshotStockWorkbench"]
