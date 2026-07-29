"""Build an industry research ranking from one exact immutable snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Literal

import duckdb

from astramind_mini.data.public import DataSnapshot

from ..contracts.ranking import IndustryResearchRankingSnapshot
from ..domain.research_ranking import SCORING_VERSION, RankingFeature, rank_industry
from .hierarchy_queries import snapshot_at, snapshot_paths
from .ranking_queries import bounded_paths, ranking_features
from .snapshot_lifecycle import SnapshotIndustryLifecycle
from .stock_evidence_queries import price_candles

REQUIRED = (
    "adjusted_market",
    "daily_basic",
    "daily_market",
    "daily_tradability",
    "industry_membership",
    "trade_calendar",
)


class SnapshotIndustryResearchRanking:
    def __init__(self, data_root: Path) -> None:
        self._root = data_root

    def current(
        self,
        *,
        industry_code: str,
        instrument_id: str | None = None,
    ) -> IndustryResearchRankingSnapshot:
        pointer = json.loads(
            (self._root / "current" / "data-snapshot.json").read_text(encoding="utf-8")
        )
        return self.load(
            data_snapshot_id=str(pointer["snapshot_id"]),
            industry_code=industry_code,
            instrument_id=instrument_id,
        )

    def load(
        self,
        *,
        data_snapshot_id: str,
        industry_code: str,
        instrument_id: str | None = None,
    ) -> IndustryResearchRankingSnapshot:
        snapshot = snapshot_at(self._root, data_snapshot_id)
        paths = snapshot_paths(self._root, snapshot)
        missing = tuple(name for name in REQUIRED if not paths.get(name))
        lifecycle = SnapshotIndustryLifecycle(self._root).load(data_snapshot_id)
        point = next(
            (item for item in lifecycle.industries if item.industry_code == industry_code),
            None,
        )
        if point is None:
            raise ValueError("请求行业不在生命周期快照中")
        lifecycle_id = _identity("lifecycle", lifecycle.model_dump(mode="json"))
        if missing or lifecycle.status == "blocked" or lifecycle.evidence_cutoff is None:
            return self._blocked(
                snapshot=snapshot,
                industry_code=industry_code,
                industry_name=point.industry_name,
                lifecycle_id=lifecycle_id,
                lifecycle_stage=point.stage,
                taxonomy_version=lifecycle.taxonomy_version or "unknown",
                evidence_cutoff=lifecycle.evidence_cutoff or snapshot.as_of.date(),
                gaps=tuple(f"missing_dataset:{name}" for name in missing) + lifecycle.known_gaps,
            )
        cutoff = lifecycle.evidence_cutoff
        paths = bounded_paths(paths, cutoff)
        market = _cached_market_features(
            str(self._root.resolve()),
            data_snapshot_id,
            cutoff.isoformat(),
        )
        features = tuple(item for item in market if item.industry_code == industry_code)
        rows = rank_industry(
            features,
            market_features=market,
            evidence_cutoff=cutoff,
            lifecycle_stage=point.stage,
        )
        selected = (
            instrument_id
            if any(item.instrument_id == instrument_id for item in rows)
            else (rows[0].instrument_id if rows else None)
        )
        with duckdb.connect(":memory:") as connection:
            candles = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=cutoff,
                period="day",
            )
            weekly = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=cutoff,
                period="week",
            )
            monthly = price_candles(
                connection,
                paths["daily_market"],
                paths["trade_calendar"],
                instrument_id=selected,
                as_of=cutoff,
                period="month",
            )
        content = _hash([item.model_dump(mode="json") for item in rows])
        status: Literal["ready", "stale", "blocked"] = (
            "stale" if lifecycle.status == "stale" else "ready"
        )
        gaps = list(lifecycle.known_gaps)
        if not rows:
            status = "blocked"
            gaps.append("industry_has_no_eligible_members")
        return IndustryResearchRankingSnapshot(
            status=status,
            ranking_snapshot_id=f"ranking:{content}",
            data_snapshot_id=data_snapshot_id,
            lifecycle_snapshot_id=lifecycle_id,
            as_of=snapshot.as_of,
            evidence_cutoff=cutoff,
            taxonomy="SW",
            taxonomy_version=lifecycle.taxonomy_version or "unknown",
            industry_code=industry_code,
            industry_name=point.industry_name,
            lifecycle_stage=point.stage,
            scoring_definition_version=SCORING_VERSION,
            member_count=len(features),
            covered_member_count=sum(item.coverage >= 0.60 for item in rows),
            content_hash=content,
            rows=rows,
            selected_instrument_id=selected,
            candles=candles,
            weekly_candles=weekly,
            monthly_candles=monthly,
            known_gaps=tuple(gaps),
        )

    @staticmethod
    def _blocked(
        *,
        snapshot: DataSnapshot,
        industry_code: str,
        industry_name: str,
        lifecycle_id: str,
        lifecycle_stage: str,
        taxonomy_version: str,
        evidence_cutoff: date,
        gaps: tuple[str, ...],
    ) -> IndustryResearchRankingSnapshot:
        content = _hash(list(gaps))
        return IndustryResearchRankingSnapshot(
            status="blocked",
            ranking_snapshot_id=f"ranking:{content}",
            data_snapshot_id=snapshot.snapshot_id,
            lifecycle_snapshot_id=lifecycle_id,
            as_of=snapshot.as_of,
            evidence_cutoff=evidence_cutoff,
            taxonomy="SW",
            taxonomy_version=taxonomy_version,
            industry_code=industry_code,
            industry_name=industry_name,
            lifecycle_stage=lifecycle_stage,
            scoring_definition_version=SCORING_VERSION,
            member_count=0,
            covered_member_count=0,
            content_hash=content,
            known_gaps=gaps,
        )


def _hash(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


def _identity(prefix: str, value: object) -> str:
    return f"{prefix}:{_hash(value)}"


@lru_cache(maxsize=2)
def _cached_market_features(
    data_root: str,
    data_snapshot_id: str,
    cutoff_text: str,
) -> tuple[RankingFeature, ...]:
    root = Path(data_root)
    snapshot = snapshot_at(root, data_snapshot_id)
    paths = bounded_paths(snapshot_paths(root, snapshot), date.fromisoformat(cutoff_text))
    with duckdb.connect(":memory:") as connection:
        return ranking_features(
            connection,
            paths,
            cutoff=date.fromisoformat(cutoff_text),
        )


__all__ = ["SnapshotIndustryResearchRanking"]
