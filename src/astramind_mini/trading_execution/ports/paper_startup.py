"""Ports for read-only Paper startup evidence."""

from __future__ import annotations

from typing import Protocol

from ..contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
    PaperStartupEvidence,
    ReadonlyCallbackHandshake,
)


class PaperStartupReader(Protocol):
    async def read(self) -> PaperStartupEvidence: ...


class PaperStartupEvidenceStore(Protocol):
    def publish_mode_lock(
        self,
        value: BrokerAccountModeLock,
        *,
        account_snapshot_id: str,
    ) -> None: ...

    def publish_handshake(self, value: ReadonlyCallbackHandshake) -> None: ...

    def publish_baseline(self, value: PaperAccountBaseline) -> None: ...


__all__ = ["PaperStartupEvidenceStore", "PaperStartupReader"]
