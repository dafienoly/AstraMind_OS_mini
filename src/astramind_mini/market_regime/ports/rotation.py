"""Ports for rotation input, immutable publication and query."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Protocol

from astramind_mini.data.public import DataSnapshot

from ..contracts import MarketRotationSnapshot
from ..domain.rotation import IndustryCloseSeries


class RotationInputSource(Protocol):
    def load(
        self, snapshot_id: str, *, required_sessions: int
    ) -> tuple[
        DataSnapshot,
        tuple[date, ...],
        tuple[IndustryCloseSeries, ...],
        tuple[str, ...],
    ]: ...


class RotationSnapshotStore(Protocol):
    def publish(self, snapshot: MarketRotationSnapshot) -> Path: ...

    def get_current(self) -> MarketRotationSnapshot: ...


__all__ = ["RotationInputSource", "RotationSnapshotStore"]
