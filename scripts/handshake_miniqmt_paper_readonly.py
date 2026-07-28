"""Run one authorized MiniQMT simulation-account read-only callback handshake."""

from __future__ import annotations

import asyncio
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters import (
    FilesystemAccountReconciliationStore,
    MiniQMTAccountError,
)
from astramind_mini.trading_execution.adapters.local_fingerprint import (
    local_fingerprint_key,
)
from astramind_mini.trading_execution.adapters.miniqmt_paper_readonly import (
    MiniQMTPaperReadonlyClient,
)
from astramind_mini.trading_execution.adapters.paper_startup_store import (
    PaperStartupStore,
)
from astramind_mini.trading_execution.application.paper_startup import PaperStartupService

ROOT = Path(__file__).resolve().parents[1]


async def handshake(settings: Settings) -> int:
    if settings.miniqmt_account_mode != "simulation":
        print(
            "blocked=simulation_mode_required "
            "recovery=将本机私有ASTRAMIND_MINIQMT_ACCOUNT_MODE准确设置为simulation"
        )
        return 2
    if settings.miniqmt_account_id is None or settings.miniqmt_userdata_path is None:
        print("blocked=missing_account_configuration recovery=配置模拟盘账户选择和userdata路径")
        return 2
    client = MiniQMTPaperReadonlyClient(
        runner=ROOT / "scripts/miniqmt_paper_readonly_runner.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        userdata_path=settings.miniqmt_userdata_path.get_secret_value(),
        account_selector=settings.miniqmt_account_id.get_secret_value(),
        account_mode=settings.miniqmt_account_mode,
        fingerprint_key=local_fingerprint_key(settings.account_reconciliation_dir),
        callback_wait_seconds=settings.miniqmt_callback_wait_seconds,
        timeout_seconds=settings.miniqmt_account_timeout_seconds
        + settings.miniqmt_callback_wait_seconds,
    )
    account_store = FilesystemAccountReconciliationStore(
        root=settings.account_reconciliation_dir,
        database=settings.shadow_db_path,
    )
    startup_store = PaperStartupStore(settings.shadow_db_path)
    try:
        publication = await PaperStartupService(
            reader=client,
            account_store=account_store,
            startup_store=startup_store,
        ).run()
    except (MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked=paper_readonly_handshake_failed error_code={code}")
        return 1
    snapshot = publication.account_snapshot
    handshake_evidence = publication.callback_handshake
    baseline = publication.account_baseline
    print(f"mode_lock_id={publication.mode_lock.mode_lock_id}")
    print(f"account_snapshot_id={snapshot.account_snapshot_id}")
    print(f"callback_handshake_id={handshake_evidence.handshake_id}")
    print(f"callback_status={handshake_evidence.status}")
    print(f"callback_count={handshake_evidence.callback_count}")
    print(f"position_count={len(snapshot.positions)}")
    print(f"open_order_count={len(baseline.open_order_fingerprints)}")
    print(f"paper_account_baseline_id={baseline.baseline_id}")
    print(f"startup_state={baseline.startup_state}")
    print(f"blocker_codes={','.join(baseline.blocker_codes)}")
    print("broker_actions_allowed=false")
    return 0


def main() -> int:
    return asyncio.run(handshake(Settings()))


if __name__ == "__main__":
    raise SystemExit(main())
