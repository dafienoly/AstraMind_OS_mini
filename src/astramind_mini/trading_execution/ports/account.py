"""Ports for read-only account evidence and reconciliation persistence."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from ..contracts.account import AccountSnapshot, ReconciliationReport


class AccountSnapshotReader(Protocol):
    async def read(self) -> AccountSnapshot: ...


class AccountReconciliationStore(Protocol):
    def publish_account_snapshot(self, snapshot: AccountSnapshot) -> Path: ...

    def publish_reconciliation(self, report: ReconciliationReport) -> Path: ...


__all__ = ["AccountReconciliationStore", "AccountSnapshotReader"]
