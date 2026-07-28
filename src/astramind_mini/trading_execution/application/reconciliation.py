"""Application orchestration for one bounded read-only startup reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..contracts.account import (
    AccountSnapshot,
    LocalAccountProjection,
    ReconciliationReport,
)
from ..domain.reconciliation import reconcile_account
from ..ports.account import AccountReconciliationStore, AccountSnapshotReader


@dataclass(frozen=True, slots=True)
class ReconciliationPublication:
    account_snapshot: AccountSnapshot
    reconciliation_report: ReconciliationReport
    account_snapshot_path: Path
    reconciliation_report_path: Path


class StartupReconciliationService:
    def __init__(
        self,
        *,
        reader: AccountSnapshotReader,
        store: AccountReconciliationStore,
    ) -> None:
        self._reader = reader
        self._store = store

    async def run(
        self,
        local_projection: LocalAccountProjection,
        *,
        created_at: datetime,
    ) -> ReconciliationPublication:
        snapshot = await self._reader.read()
        report = reconcile_account(local_projection, snapshot, created_at=created_at)
        snapshot_path = self._store.publish_account_snapshot(snapshot)
        report_path = self._store.publish_reconciliation(report)
        return ReconciliationPublication(
            account_snapshot=snapshot,
            reconciliation_report=report,
            account_snapshot_path=snapshot_path,
            reconciliation_report_path=report_path,
        )


__all__ = ["ReconciliationPublication", "StartupReconciliationService"]
