"""Restore already-published ETF datasets into the current DataSnapshot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DataControlLedger,
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application.snapshot_reconciliation import (
    SnapshotDatasetReconciler,
)

ETF_DATASETS = (
    "etf_daily",
    "etf_industry_mapping",
    "etf_master",
    "etf_share",
)


def main() -> int:
    settings = Settings()
    current = _current_snapshot_id(settings.data_dir)
    donor = _latest_complete_etf_snapshot(settings.data_dir, exclude=current)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    result = SnapshotDatasetReconciler(
        data_root=settings.data_dir,
        datasets=FilesystemDatasetStore(settings.data_dir),
        snapshots=FilesystemSnapshotStore(settings.data_dir),
        ledger=ledger,
    ).restore(
        base_snapshot_id=current,
        donor_snapshot_id=donor,
        dataset_names=ETF_DATASETS,
        created_at=datetime.now(UTC),
        code_identity="wp-0043-etf-snapshot-reconciliation-v1",
        donor_gap_prefixes=("etf_",),
    )
    print(f"base_snapshot_id={current}")
    print(f"donor_snapshot_id={donor}")
    print(f"snapshot_id={result.snapshot.snapshot_id}")
    print("restored_datasets=" + ",".join(result.restored_datasets))
    print("broker_actions_allowed=false")
    return 0


def _current_snapshot_id(root: Path) -> str:
    value = json.loads((root / "current/data-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id = value.get("snapshot_id") if isinstance(value, dict) else None
    if not isinstance(snapshot_id, str):
        raise ValueError("当前 DataSnapshot 指针无效")
    return snapshot_id


def _latest_complete_etf_snapshot(root: Path, *, exclude: str) -> str:
    candidates: list[tuple[datetime, str]] = []
    required = set(ETF_DATASETS)
    for path in (root / "snapshots").glob("*/manifest.json"):
        value = json.loads(path.read_text(encoding="utf-8"))
        snapshot_id = value.get("snapshot_id")
        datasets = value.get("datasets")
        if not isinstance(snapshot_id, str) or snapshot_id == exclude:
            continue
        names = (
            {item.get("dataset_name") for item in datasets if isinstance(item, dict)}
            if isinstance(datasets, list)
            else set()
        )
        if required <= names:
            created_at = datetime.fromisoformat(str(value["created_at"]).replace("Z", "+00:00"))
            candidates.append((created_at, snapshot_id))
    if not candidates:
        raise ValueError("没有可恢复的完整 ETF 数据快照")
    return max(candidates)[1]


if __name__ == "__main__":
    raise SystemExit(main())
