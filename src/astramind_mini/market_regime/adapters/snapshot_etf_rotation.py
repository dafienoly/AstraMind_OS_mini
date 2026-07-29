"""Build ETF rotation research from one exact immutable DataSnapshot."""

from __future__ import annotations

import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..contracts.etf_rotation import (
    EtfFunnel,
    EtfRotationCandidate,
    EtfRotationProjection,
)
from ..domain.etf_rotation import (
    SPREAD_PROXY_THRESHOLD_BPS,
    STRATEGY_VERSION,
    TRACKING_PROXY_THRESHOLD,
    CandidateInput,
    blocked_replay,
    build_target_draft,
    evaluate_candidate,
)
from ..domain.identity import content_hash
from .etf_rotation_queries import (
    expected_cutoff,
    load_industry_closes,
    load_prices,
    parquet_paths,
)
from .snapshot_lifecycle import SnapshotIndustryLifecycle

REQUIRED_DATASETS = (
    "etf_daily",
    "etf_industry_mapping",
    "etf_master",
    "etf_share",
    "industry_index_daily",
    "trade_calendar",
)


class SnapshotEtfRotation:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(self, selected_etf_code: str | None = None) -> EtfRotationProjection:
        pointer = json.loads(
            (self._root / "current/data-snapshot.json").read_text(encoding="utf-8")
        )
        if not isinstance(pointer, dict) or not isinstance(pointer.get("snapshot_id"), str):
            raise ValueError("当前数据快照指针无效")
        return self.load(pointer["snapshot_id"], selected_etf_code=selected_etf_code)

    def load(
        self,
        snapshot_id: str,
        *,
        selected_etf_code: str | None = None,
    ) -> EtfRotationProjection:
        projection = _cached_projection(str(self._root.resolve()), snapshot_id)
        if selected_etf_code is None:
            return projection
        if not any(item.etf_code == selected_etf_code for item in projection.candidates):
            raise ValueError("所选 ETF 不在当前轮动投影")
        return projection.model_copy(update={"selected_etf_code": selected_etf_code})

    def _build(self, snapshot_id: str) -> EtfRotationProjection:
        snapshot = self._snapshot(snapshot_id)
        references = {item.dataset_name: item for item in snapshot.datasets}
        missing = tuple(name for name in REQUIRED_DATASETS if name not in references)
        if missing:
            return self._blocked(snapshot, tuple(f"missing_dataset:{name}" for name in missing))
        paths = {
            name: self._paths(name, references[name].dataset_version, references[name].content_hash)
            for name in REQUIRED_DATASETS
        }
        lifecycle = SnapshotIndustryLifecycle(self._root).load(snapshot.snapshot_id)
        with duckdb.connect(":memory:") as connection:
            decision_cutoff = expected_cutoff(
                connection,
                paths["trade_calendar"],
                snapshot.as_of,
            )
            candidates, mapping_version, start, end = self._candidates(
                connection,
                paths,
                snapshot,
                decision_cutoff,
                lifecycle,
            )
        target = build_target_draft(candidates)
        replay = blocked_replay(
            start_date=start,
            end_date=end,
            mapping_effective_from=date(2026, 7, 29),
        )
        active = tuple(
            item
            for item in candidates
            if item.mapping_tier == "exact" and item.state != "unavailable"
        )
        funnel = EtfFunnel(
            industry_count=len({item.industry_code for item in candidates}),
            exact_mapping_count=len(active),
            foundation_count=sum(
                item.state not in {"unavailable", "context_only", "stale"}
                for item in candidates
                if item.mapping_tier == "exact"
            ),
            evidence_gate_count=sum(item.state in {"eligible", "rejected"} for item in candidates),
            eligible_count=sum(item.state == "eligible" for item in candidates),
        )
        selected = next(
            (item.etf_code for item in candidates if item.state == "eligible"),
            next((item.etf_code for item in candidates if item.candles and item.etf_code), None),
        )
        gaps = list(
            dict.fromkeys(
                (
                    *snapshot.known_gaps,
                    *lifecycle.known_gaps,
                    "spread_uses_corwin_schultz_ohlc_proxy",
                    "tracking_uses_sw_l1_exposure_proxy",
                    *(() if active else ("etf_mapping_not_effective_at_snapshot_as_of",)),
                )
            )
        )
        status: Literal["ready", "stale", "blocked"] = (
            "blocked"
            if not active
            else "stale"
            if lifecycle.status == "stale"
            or any(item.state == "stale" for item in candidates if item.mapping_tier == "exact")
            else "ready"
        )
        identity = content_hash(
            {
                "data_snapshot_id": snapshot.snapshot_id,
                "strategy_version": STRATEGY_VERSION,
                "mapping_version": mapping_version,
                "candidates": [item.model_dump(mode="json") for item in candidates],
                "target": target.model_dump(mode="json"),
                "replay": replay.model_dump(mode="json"),
            }
        )
        return EtfRotationProjection(
            status=status,
            rotation_snapshot_id=f"etf-rotation:{identity}",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of,
            evidence_cutoff=decision_cutoff,
            strategy_version=STRATEGY_VERSION,
            mapping_version=mapping_version,
            spread_proxy_threshold_bps=SPREAD_PROXY_THRESHOLD_BPS,
            tracking_proxy_threshold=TRACKING_PROXY_THRESHOLD,
            funnel=funnel,
            candidates=candidates,
            target_draft=target,
            replay=replay,
            selected_etf_code=selected,
            known_gaps=tuple(gaps),
        )

    def _candidates(
        self,
        connection: duckdb.DuckDBPyConnection,
        paths: dict[str, tuple[Path, ...]],
        snapshot: DataSnapshot,
        cutoff: date,
        lifecycle: Any,
    ) -> tuple[tuple[EtfRotationCandidate, ...], str, date | None, date | None]:
        mappings = connection.execute(
            """
            SELECT industry_code, industry_name, etf_code, semantic_tier,
                   eligible_for_foundation, effective_from, effective_to,
                   mapping_version, available_at
            FROM read_parquet(?) ORDER BY industry_code, etf_code
            """,
            [parquet_paths(paths["etf_industry_mapping"])],
        ).fetchall()
        versions = {str(row[7]) for row in mappings}
        if len(versions) != 1:
            raise ValueError("ETF 映射版本不唯一")
        masters = {
            str(row[0]): (str(row[1]), str(row[2]) == "L")
            for row in connection.execute(
                """
                SELECT instrument_id, name, list_status FROM read_parquet(?)
                WHERE available_at <= ?
                """,
                [parquet_paths(paths["etf_master"]), snapshot.as_of],
            ).fetchall()
        }
        shares = {
            str(row[0]): float(row[1])
            for row in connection.execute(
                """
                SELECT instrument_id, arg_max(fund_share, trade_date)
                FROM read_parquet(?) WHERE trade_date <= ? AND available_at <= ?
                GROUP BY instrument_id
                """,
                [parquet_paths(paths["etf_share"]), cutoff, snapshot.as_of],
            ).fetchall()
        }
        prices, start, end = load_prices(connection, paths["etf_daily"], cutoff)
        industry = load_industry_closes(connection, paths["industry_index_daily"], cutoff)
        lifecycle_by_code = {item.industry_code: item for item in lifecycle.industries}
        result = []
        for row in mappings:
            code = str(row[2]) if row[2] is not None else None
            point = lifecycle_by_code.get(str(row[0]))
            active = (
                row[5] <= snapshot.as_of.date()
                and (row[6] is None or snapshot.as_of.date() < row[6])
                and row[8] <= snapshot.as_of
            )
            name, listed = masters.get(code or "", (None, False))
            result.append(
                evaluate_candidate(
                    CandidateInput(
                        industry_code=str(row[0]),
                        industry_name=str(row[1]),
                        lifecycle_stage=point.stage if point else "方向未明",
                        lifecycle_confidence=point.confidence if point else "low",
                        etf_code=code,
                        etf_name=name,
                        mapping_tier=str(row[3]),
                        mapping_eligible=bool(row[4]),
                        mapping_active=active,
                        decision_cutoff=cutoff,
                        prices=tuple(prices.get(code or "", ())),
                        industry_closes=tuple(industry.get(str(row[0]), ())),
                        latest_fund_share=shares.get(code or ""),
                        master_listed=listed,
                    )
                )
            )
        return tuple(result), versions.pop(), start, end

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = _digest(snapshot_id, "snapshot:sha256")
        snapshot = DataSnapshot.model_validate_json(
            (self._root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
        )
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("ETF 轮动快照身份与路径不一致")
        return snapshot

    def _paths(self, name: str, version: str, expected_hash: str) -> tuple[Path, ...]:
        directory = self._root / "datasets" / name / _digest(version, "sha256")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        if (
            manifest.get("dataset_version") != version
            or manifest.get("content_hash") != expected_hash
        ):
            raise ValueError(f"ETF 轮动数据集身份冲突：{name}")
        artifacts = manifest.get("artifact_paths")
        if not isinstance(artifacts, list):
            raise ValueError(f"ETF 轮动数据集制品无效：{name}")
        paths = tuple(directory / str(item) for item in artifacts if str(item).endswith(".parquet"))
        if not paths or any(not path.is_file() for path in paths):
            raise ValueError(f"ETF 轮动数据集制品缺失：{name}")
        return paths

    def _blocked(
        self,
        snapshot: DataSnapshot,
        gaps: tuple[str, ...],
    ) -> EtfRotationProjection:
        target = build_target_draft(())
        replay = blocked_replay(
            start_date=None,
            end_date=None,
            mapping_effective_from=date(2026, 7, 29),
        )
        return EtfRotationProjection(
            status="blocked",
            rotation_snapshot_id=f"etf-rotation:{content_hash((snapshot.snapshot_id, gaps))}",
            data_snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of,
            strategy_version=STRATEGY_VERSION,
            mapping_version="unavailable",
            spread_proxy_threshold_bps=SPREAD_PROXY_THRESHOLD_BPS,
            tracking_proxy_threshold=TRACKING_PROXY_THRESHOLD,
            funnel=EtfFunnel(
                industry_count=0,
                exact_mapping_count=0,
                foundation_count=0,
                evidence_gate_count=0,
                eligible_count=0,
            ),
            target_draft=target,
            replay=replay,
            known_gaps=gaps,
        )


def _digest(identity: str, prefix: str) -> str:
    value = identity.removeprefix(prefix + ":")
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"非法内容身份：{identity}")
    return value


@lru_cache(maxsize=8)
def _cached_projection(root: str, snapshot_id: str) -> EtfRotationProjection:
    return SnapshotEtfRotation(Path(root))._build(snapshot_id)


__all__ = ["SnapshotEtfRotation"]
