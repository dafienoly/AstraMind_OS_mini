"""Explicit local-only recovery for immutable dataset artifacts."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.data.adapters import (
    DataControlLedger,
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application.immutable_recovery import (
    ImmutableArtifactRecoveryService,
    load_recovery_plan,
)

APPLY_CONFIRMATION = "REPUBLISH_IMMUTABLE_SNAPSHOT"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="从显式本地文件发布新数据集身份并原子切换 DataSnapshot"
    )
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--control-db", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--apply", required=True)
    args = parser.parse_args()
    if args.apply != APPLY_CONFIRMATION:
        raise ValueError(f"--apply 必须准确等于 {APPLY_CONFIRMATION}")

    data_root = args.data_root.expanduser().resolve()
    control_db = args.control_db.expanduser().resolve()
    base_snapshot_id, datasets = load_recovery_plan(args.plan.expanduser().resolve())
    ledger = DataControlLedger(control_db)
    ledger.migrate()
    result = ImmutableArtifactRecoveryService(
        data_root=data_root,
        datasets=FilesystemDatasetStore(data_root),
        snapshots=FilesystemSnapshotStore(data_root),
        ledger=ledger,
    ).recover(
        base_snapshot_id=base_snapshot_id,
        dataset_sources=datasets,
        created_at=datetime.now(UTC),
        code_identity="wp-0057-immutable-artifact-recovery-v1",
    )
    print(f"base_snapshot_id={base_snapshot_id}")
    print(f"snapshot_id={result.snapshot.snapshot_id}")
    print("recovered_datasets=" + ",".join(result.recovered_datasets))
    print(f"recovery_report={result.recovery_report_path}")
    print("provider_network_calls=0")
    print("broker_actions_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
