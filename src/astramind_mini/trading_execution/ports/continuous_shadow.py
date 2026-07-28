"""Ports for append-only continuous Shadow persistence."""

from __future__ import annotations

from typing import Protocol

from astramind_mini.contracts import ExecutionEvent

from ..contracts.continuous_shadow import (
    ContinuousShadowCycle,
    ContinuousShadowOrderPlan,
    ContinuousShadowState,
    ReconciliationDisposition,
)


class ContinuousShadowRepository(Protocol):
    def publish_disposition(self, value: ReconciliationDisposition) -> None: ...

    def publish_state(self, value: ContinuousShadowState) -> None: ...

    def publish_order_plan(self, value: ContinuousShadowOrderPlan) -> None: ...

    def publish_cycle(self, value: ContinuousShadowCycle) -> None: ...

    def append_shadow_event(self, event: ExecutionEvent, payload: object) -> None: ...


__all__ = ["ContinuousShadowRepository"]
