"""Composition helpers for explicitly invoked Paper canary commands."""

from __future__ import annotations

from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters.account_store import (
    FilesystemAccountReconciliationStore,
)
from astramind_mini.trading_execution.adapters.local_fingerprint import (
    local_fingerprint_key,
)
from astramind_mini.trading_execution.adapters.miniqmt_canary_quote import (
    MiniQMTCanaryQuoteReader,
)
from astramind_mini.trading_execution.adapters.miniqmt_paper_gateway import (
    MiniQMTPaperGateway,
)
from astramind_mini.trading_execution.adapters.miniqmt_paper_readonly import (
    MiniQMTPaperReadonlyClient,
)
from astramind_mini.trading_execution.adapters.paper_startup_store import PaperStartupStore
from astramind_mini.trading_execution.application.paper_startup import (
    PaperStartupPublication,
    PaperStartupService,
)

ROOT = Path(__file__).resolve().parents[2]


def account_store(settings: Settings) -> FilesystemAccountReconciliationStore:
    return FilesystemAccountReconciliationStore(
        root=settings.account_reconciliation_dir,
        database=settings.shadow_db_path,
    )


async def fresh_startup(settings: Settings) -> PaperStartupPublication:
    if (
        settings.miniqmt_account_mode != "simulation"
        or settings.miniqmt_account_id is None
        or settings.miniqmt_userdata_path is None
    ):
        raise ValueError("simulation_account_configuration_required")
    key = local_fingerprint_key(settings.account_reconciliation_dir)
    client = MiniQMTPaperReadonlyClient(
        runner=ROOT / "scripts/miniqmt_paper_readonly_runner.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        userdata_path=settings.miniqmt_userdata_path.get_secret_value(),
        account_selector=settings.miniqmt_account_id.get_secret_value(),
        account_mode=settings.miniqmt_account_mode,
        fingerprint_key=key,
        callback_wait_seconds=settings.miniqmt_callback_wait_seconds,
        timeout_seconds=(
            settings.miniqmt_account_timeout_seconds + settings.miniqmt_callback_wait_seconds
        ),
        diagnostic_root=settings.shadow_db_path.parent / "paper-canary/runner-diagnostics",
    )
    return await PaperStartupService(
        reader=client,
        account_store=account_store(settings),
        startup_store=PaperStartupStore(settings.shadow_db_path),
    ).run()


def quote_reader(settings: Settings) -> MiniQMTCanaryQuoteReader:
    return MiniQMTCanaryQuoteReader(
        runner=ROOT / "scripts/windows/miniqmt_canary_quote.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        quote_port=settings.miniqmt_quote_port,
        timeout_seconds=settings.miniqmt_probe_timeout_seconds,
        fresh_wait_seconds=settings.miniqmt_fresh_tick_wait_seconds,
        diagnostic_root=settings.shadow_db_path.parent / "paper-canary/runner-diagnostics",
    )


def paper_gateway(settings: Settings) -> MiniQMTPaperGateway:
    if (
        settings.miniqmt_account_mode != "simulation"
        or settings.miniqmt_account_id is None
        or settings.miniqmt_userdata_path is None
    ):
        raise ValueError("simulation_account_configuration_required")
    return MiniQMTPaperGateway(
        runner=ROOT / "scripts/miniqmt_paper_gateway_runner.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        userdata_path=settings.miniqmt_userdata_path.get_secret_value(),
        account_selector=settings.miniqmt_account_id.get_secret_value(),
        account_mode=settings.miniqmt_account_mode,
        fingerprint_key=local_fingerprint_key(settings.account_reconciliation_dir),
        quote_port=settings.miniqmt_quote_port,
        timeout_seconds=settings.miniqmt_account_timeout_seconds,
        diagnostic_root=settings.shadow_db_path.parent / "paper-canary/runner-diagnostics",
    )


__all__ = ["account_store", "fresh_startup", "paper_gateway", "quote_reader"]
