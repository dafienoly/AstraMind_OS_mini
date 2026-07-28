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
from ..contracts.shadow_cycle import ShadowCycleCheckpoint, ShadowCycleResult


class ContinuousShadowRepository(Protocol):
    def publish_disposition(self, value: ReconciliationDisposition) -> None: ...

    def publish_state(self, value: ContinuousShadowState) -> None: ...

    def publish_order_plan(self, value: ContinuousShadowOrderPlan) -> None: ...

    def publish_cycle(self, value: ContinuousShadowCycle) -> None: ...

    def append_shadow_event(self, event: ExecutionEvent, payload: object) -> None: ...

    def read_state(self, identity: str) -> ContinuousShadowState: ...

    def publish_checkpoint(self, value: ShadowCycleCheckpoint) -> None: ...

    def latest_checkpoint(self, cycle_id: str) -> ShadowCycleCheckpoint | None: ...

    def checkpoints_for(self, cycle_id: str) -> tuple[ShadowCycleCheckpoint, ...]: ...

    def publish_result(self, value: ShadowCycleResult) -> None: ...

    def read_result_for_cycle(self, cycle_id: str) -> ShadowCycleResult | None: ...

    def event_count_for_cycle(self, cycle_id: str) -> int: ...


__all__ = ["ContinuousShadowRepository"]
