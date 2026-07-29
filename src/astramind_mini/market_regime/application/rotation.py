"""Application service for formal industry relative rotation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..contracts import MarketRotationSnapshot, RotationFormula
from ..domain.rotation import build_rotation_snapshot
from ..ports import RotationInputSource, RotationSnapshotStore


def production_formula() -> RotationFormula:
    return RotationFormula(
        formula_version="rotation-index-ew-v1.0.0",
        benchmark_id="SW2021:L1:equal_weight_index_return",
        benchmark_definition_version="1.0.0",
        taxonomy="SW",
        taxonomy_version="SW2021",
        fast_window=20,
        slow_window=60,
        momentum_window=5,
        warmup_sessions=140,
        output_sessions=60,
        scale=5.0,
        clip_z=3.0,
        neutral_band=0.25,
        confirmation_sessions=2,
        required_industry_coverage=1.0,
        minimum_constituent_count=3,
        rounding_decimals=6,
    )


@dataclass(frozen=True, slots=True)
class RotationPublication:
    snapshot: MarketRotationSnapshot
    path: Path


class MarketRotationService:
    def __init__(self, *, source: RotationInputSource, store: RotationSnapshotStore) -> None:
        self._source = source
        self._store = store

    def publish(self, data_snapshot_id: str) -> RotationPublication:
        snapshot = self.build(data_snapshot_id)
        return RotationPublication(snapshot=snapshot, path=self._store.publish(snapshot))

    def build(self, data_snapshot_id: str) -> MarketRotationSnapshot:
        formula = production_formula()
        data_snapshot, calendar, industries, gaps = self._source.load(
            data_snapshot_id, required_sessions=formula.warmup_sessions + 1
        )
        return build_rotation_snapshot(
            data_snapshot_id=data_snapshot.snapshot_id,
            as_of=data_snapshot.as_of,
            created_at=data_snapshot.created_at,
            calendar=calendar,
            industries=industries,
            formula=formula,
            known_gaps=(*gaps, "price_relative_strength_proxy_not_direct_capital_flow"),
        )


__all__ = ["MarketRotationService", "RotationPublication", "production_formula"]
