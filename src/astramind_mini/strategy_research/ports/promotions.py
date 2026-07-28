"""Persistence port for explicit local strategy-promotion decisions."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from ..contracts import PromotionDecision
from ..domain.sealed_models import ReplayCandidate, ReplayPrice


class PromotionDecisionStore(Protocol):
    def append(self, decision: PromotionDecision) -> None: ...

    def get(self, decision_id: str) -> PromotionDecision: ...

    def latest_promoted(self, sleeve: str) -> PromotionDecision | None: ...


class SealedReplaySource(Protocol):
    def trading_dates(self, *, start_date: date, end_date: date) -> tuple[date, ...]: ...

    def candidates(
        self,
        *,
        family: str,
        horizon_sessions: int,
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayCandidate, ...]: ...

    def prices(
        self,
        *,
        instruments: tuple[str, ...],
        start_date: date,
        end_date: date,
    ) -> tuple[ReplayPrice, ...]: ...


__all__ = ["PromotionDecisionStore", "SealedReplaySource"]
