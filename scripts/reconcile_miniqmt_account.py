"""Run one explicitly configured, read-only MiniQMT startup reconciliation."""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters import (
    FilesystemAccountReconciliationStore,
    MiniQMTAccountClient,
    MiniQMTAccountError,
)
from astramind_mini.trading_execution.application import StartupReconciliationService
from astramind_mini.trading_execution.domain import synthetic_shadow_projection

ROOT = Path(__file__).resolve().parents[1]


def _fingerprint_key(root: Path) -> str:
    path = root / "fingerprint.key"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(secrets.token_hex(32))
    return path.read_text(encoding="utf-8").strip()


async def reconcile(settings: Settings) -> int:
    if (
        settings.miniqmt_account_mode is None
        or settings.miniqmt_account_id is None
        or settings.miniqmt_userdata_path is None
    ):
        print(
            "blocked=missing_account_configuration "
            "recovery=在.env.local配置ASTRAMIND_MINIQMT_ACCOUNT_MODE、"
            "ASTRAMIND_MINIQMT_ACCOUNT_ID和ASTRAMIND_MINIQMT_USERDATA_PATH"
        )
        return 2
    reader = MiniQMTAccountClient(
        runner=ROOT / "scripts/miniqmt_account_runner.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        userdata_path=settings.miniqmt_userdata_path.get_secret_value(),
        account_selector=settings.miniqmt_account_id.get_secret_value(),
        account_mode=settings.miniqmt_account_mode,
        fingerprint_key=_fingerprint_key(settings.account_reconciliation_dir),
        timeout_seconds=settings.miniqmt_account_timeout_seconds,
    )
    store = FilesystemAccountReconciliationStore(
        root=settings.account_reconciliation_dir,
        database=settings.shadow_db_path,
    )
    now = datetime.now(UTC)
    local = synthetic_shadow_projection(as_of=now)
    try:
        publication = await StartupReconciliationService(reader=reader, store=store).run(
            local,
            created_at=now,
        )
    except (MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked=account_reconciliation_failed error_code={code}")
        return 1
    snapshot = publication.account_snapshot
    report = publication.reconciliation_report
    print(f"account_snapshot_id={snapshot.account_snapshot_id}")
    print(f"account_mode={snapshot.account_mode}")
    print(f"position_count={len(snapshot.positions)}")
    print(f"order_count={len(snapshot.orders)}")
    print(f"trade_count={len(snapshot.trades)}")
    print(f"reconciliation_report_id={report.reconciliation_report_id}")
    print(f"status={report.status}")
    print(f"broker_actions_allowed={str(report.broker_actions_allowed).lower()}")
    print(f"blocker_codes={','.join(report.blocker_codes) or 'none'}")
    return 0


def main() -> int:
    return asyncio.run(reconcile(Settings()))


if __name__ == "__main__":
    raise SystemExit(main())
