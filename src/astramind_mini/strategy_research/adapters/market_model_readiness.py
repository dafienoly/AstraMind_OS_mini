"""Read-only production-data readiness audit for the five market-model families."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from astramind_mini.contracts import DataSnapshot
from astramind_mini.data.public import DatasetManifest
from astramind_mini.strategy_research.market_models.contracts import MarketModelFamily


@dataclass(frozen=True)
class MarketModelReadinessItem:
    model_family: MarketModelFamily
    development_ready: bool
    supportive_evidence_ready: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class MarketModelReadinessReport:
    data_snapshot_id: str
    as_of: str
    models: tuple[MarketModelReadinessItem, ...]
    broker_actions_allowed: bool = False


class MarketModelReadinessReader:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(self) -> MarketModelReadinessReport:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        snapshot_id = pointer.get("snapshot_id") if isinstance(pointer, dict) else None
        if not isinstance(snapshot_id, str):
            raise ValueError("当前 DataSnapshot 指针无效")
        snapshot = self._snapshot(snapshot_id)
        manifests = {
            reference.dataset_name: self._manifest(
                reference.dataset_name,
                reference.dataset_version,
                reference.content_hash,
            )
            for reference in snapshot.datasets
        }
        membership_blocked = _has_gap(
            manifests,
            "industry_membership",
            "historical_membership_publication_time_unavailable",
        )
        price_ready = _covers(
            manifests,
            ("industry_index_daily", "official_index_daily"),
            start_on_or_before=date(2012, 1, 1),
        )
        price_reasons = []
        if not price_ready:
            price_reasons.append("ten_year_price_window_incomplete")
        if membership_blocked:
            price_reasons.append("historical_breadth_membership_not_then_known")
        price_families: tuple[MarketModelFamily, ...] = (
            "industry_heat",
            "industry_rotation",
        )
        items = [
            MarketModelReadinessItem(
                model_family=family,
                development_ready=price_ready,
                supportive_evidence_ready=price_ready and not membership_blocked,
                reason_codes=tuple(price_reasons),
            )
            for family in price_families
        ]
        items.extend(
            self._membership_models(manifests, membership_blocked),
        )
        items.append(self._etf_model(manifests))
        return MarketModelReadinessReport(
            data_snapshot_id=snapshot.snapshot_id,
            as_of=snapshot.as_of.isoformat(),
            models=tuple(items),
        )

    def _membership_models(
        self,
        manifests: dict[str, DatasetManifest],
        membership_blocked: bool,
    ) -> tuple[MarketModelReadinessItem, ...]:
        common = {
            "industry_membership",
            "daily_market",
            "daily_basic",
            "industry_index_daily",
        }
        missing = tuple(sorted(common - manifests.keys()))
        reasons = [*(f"missing_dataset:{name}" for name in missing)]
        if membership_blocked:
            reasons.append("historical_membership_not_then_known")
        ready = not reasons
        membership_families: tuple[MarketModelFamily, ...] = (
            "industry_lifecycle",
            "industry_research_ranking",
        )
        return tuple(
            MarketModelReadinessItem(
                model_family=family,
                development_ready=ready,
                supportive_evidence_ready=ready,
                reason_codes=tuple(reasons),
            )
            for family in membership_families
        )

    def _etf_model(
        self,
        manifests: dict[str, DatasetManifest],
    ) -> MarketModelReadinessItem:
        required = {
            "etf_daily",
            "etf_nav",
            "etf_official_benchmark",
            "official_index_daily",
        }
        reasons = [*(f"missing_dataset:{name}" for name in sorted(required - manifests.keys()))]
        if _has_gap(
            manifests,
            "etf_official_benchmark",
            "historical_mapping_availability_unknown",
        ):
            reasons.append("official_benchmark_mapping_not_then_known")
        spread_sessions = len(
            tuple((self._root / "realtime" / "miniqmt" / "etf-spread").glob("market-date=*"))
        )
        if spread_sessions < 60:
            reasons.append(f"l1_spread_sessions:{spread_sessions}/60")
        ready = not reasons
        return MarketModelReadinessItem(
            model_family="etf_rotation",
            development_ready=ready,
            supportive_evidence_ready=ready,
            reason_codes=tuple(reasons),
        )

    def _snapshot(self, snapshot_id: str) -> DataSnapshot:
        digest = snapshot_id.rsplit(":", 1)[-1]
        snapshot = DataSnapshot.model_validate_json(
            (self._root / "snapshots" / digest / "manifest.json").read_text(encoding="utf-8")
        )
        if snapshot.snapshot_id != snapshot_id:
            raise ValueError("DataSnapshot 身份与路径不一致")
        return snapshot

    def _manifest(
        self,
        name: str,
        version: str,
        expected_hash: str,
    ) -> DatasetManifest:
        digest = version.removeprefix("sha256:")
        manifest = DatasetManifest.model_validate_json(
            (self._root / "datasets" / name / digest / "manifest.json").read_text(encoding="utf-8")
        )
        if manifest.dataset_version != version or manifest.content_hash != expected_hash:
            raise ValueError(f"数据集身份冲突：{name}")
        return manifest


def _has_gap(
    manifests: dict[str, DatasetManifest],
    name: str,
    gap: str,
) -> bool:
    manifest = manifests.get(name)
    return manifest is None or gap in manifest.known_gaps


def _covers(
    manifests: dict[str, DatasetManifest],
    names: tuple[str, ...],
    *,
    start_on_or_before: date,
) -> bool:
    return all(
        name in manifests and manifests[name].date_range[0] <= start_on_or_before for name in names
    )


__all__ = [
    "MarketModelReadinessItem",
    "MarketModelReadinessReader",
    "MarketModelReadinessReport",
]
