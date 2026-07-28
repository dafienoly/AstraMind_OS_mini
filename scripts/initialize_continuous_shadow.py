"""Resolve WP-0011 differences without adopting broker state into local Shadow."""

from __future__ import annotations

import argparse

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters import (
    ContinuousShadowStore,
    FilesystemAccountReconciliationStore,
)
from astramind_mini.trading_execution.application import ContinuousShadowService
from astramind_mini.trading_execution.domain import synthetic_shadow_projection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--account-snapshot-id", required=True)
    parser.add_argument("--reconciliation-report-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    evidence = FilesystemAccountReconciliationStore(
        root=settings.account_reconciliation_dir,
        database=settings.shadow_db_path,
    )
    snapshot = evidence.read_account_snapshot(args.account_snapshot_id)
    report = evidence.read_reconciliation(args.reconciliation_report_id)
    local = synthetic_shadow_projection(as_of=report.created_at)
    store = ContinuousShadowStore(settings.shadow_db_path)
    disposition, state = ContinuousShadowService(store).initialize(
        local=local,
        snapshot=snapshot,
        report=report,
    )
    print(f"disposition_id={disposition.disposition_id}")
    print(f"resolution_kind={disposition.resolution_kind}")
    print(f"local_shadow_state_id={state.state_id}")
    print(f"local_shadow_allowed={str(disposition.local_shadow_allowed).lower()}")
    print(f"broker_actions_allowed={str(disposition.broker_actions_allowed).lower()}")
    print("next_status=waiting_for_promoted_portfolio_target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
