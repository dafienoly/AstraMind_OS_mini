"""Publish one complete, read-only Paper account startup baseline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..contracts.account import AccountSnapshot
from ..contracts.paper_startup import (
    BrokerAccountModeLock,
    PaperAccountBaseline,
    ReadonlyCallbackHandshake,
)
from ..ports.account import AccountReconciliationStore
from ..ports.paper_startup import PaperStartupEvidenceStore, PaperStartupReader


@dataclass(frozen=True, slots=True)
class PaperStartupPublication:
    mode_lock: BrokerAccountModeLock
    account_snapshot: AccountSnapshot
    callback_handshake: ReadonlyCallbackHandshake
    account_baseline: PaperAccountBaseline
    account_snapshot_path: Path


class PaperStartupService:
    def __init__(
        self,
        *,
        reader: PaperStartupReader,
        account_store: AccountReconciliationStore,
        startup_store: PaperStartupEvidenceStore,
    ) -> None:
        self._reader = reader
        self._account_store = account_store
        self._startup_store = startup_store

    async def run(self) -> PaperStartupPublication:
        value = await self._reader.read()
        snapshot_path = self._account_store.publish_account_snapshot(value.account_snapshot)
        self._startup_store.publish_mode_lock(
            value.mode_lock,
            account_snapshot_id=value.account_snapshot.account_snapshot_id,
        )
        self._startup_store.publish_handshake(value.callback_handshake)
        self._startup_store.publish_baseline(value.account_baseline)
        return PaperStartupPublication(
            mode_lock=value.mode_lock,
            account_snapshot=value.account_snapshot,
            callback_handshake=value.callback_handshake,
            account_baseline=value.account_baseline,
            account_snapshot_path=snapshot_path,
        )


__all__ = ["PaperStartupPublication", "PaperStartupService"]
