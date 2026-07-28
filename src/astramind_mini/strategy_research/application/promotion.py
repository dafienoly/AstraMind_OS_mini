"""Explicit manual promotion with no broker side effect."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from ..contracts import EvidenceBundle, PromotionDecision
from ..ports import PromotionDecisionStore
from .identity import research_hash


class ManualPromotionService:
    def __init__(self, store: PromotionDecisionStore) -> None:
        self._store = store

    def decide(
        self,
        *,
        bundle: EvidenceBundle,
        evidence_id: str,
        strategy_version_id: str,
        outcome: Literal["promoted", "rejected"],
        rationale: str,
        decided_at: datetime,
    ) -> PromotionDecision:
        if not rationale.strip():
            raise ValueError("晋级决定必须包含理由")
        matches = [
            item
            for item in bundle.evidence
            if item.evidence_id == evidence_id and item.strategy_version_id == strategy_version_id
        ]
        if len(matches) != 1:
            raise ValueError("晋级决定未精确匹配封存证据与策略版本")
        identity = {
            "strategy_version_id": strategy_version_id,
            "evidence_bundle_id": bundle.bundle_id,
            "evidence_id": evidence_id,
            "sleeve": "tactical",
            "outcome": outcome,
            "rationale": rationale.strip(),
            "decided_at": decided_at,
        }
        decision = PromotionDecision(
            decision_id="promotion:" + research_hash(identity),
            strategy_version_id=strategy_version_id,
            evidence_bundle_id=bundle.bundle_id,
            evidence_id=evidence_id,
            sleeve="tactical",
            outcome=outcome,
            rationale=rationale.strip(),
            decided_at=decided_at,
            broker_enabled=False,
        )
        self._store.append(decision)
        return decision


__all__ = ["ManualPromotionService"]
