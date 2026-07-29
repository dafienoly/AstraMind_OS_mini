"""Publish the WP-0043 ETF data foundation without any broker action."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    TushareHttpClient,
    load_tushare_probe_config,
)
from astramind_mini.data.etf_foundation import EtfFoundationService


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    base_snapshot_id = args.base_snapshot_id or _current_snapshot(settings.data_dir)
    config = load_tushare_probe_config(settings, args.provider_env_file)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    publication = await EtfFoundationService(
        data_root=settings.data_dir,
        provider=TushareHttpClient(config),
        raw_store=FilesystemRawRecordStore(settings.data_dir),
        encoder=DuckDBParquetEncoder(),
        dataset_store=FilesystemDatasetStore(settings.data_dir),
        snapshot_store=FilesystemSnapshotStore(settings.data_dir),
        ledger=ledger,
    ).run(
        base_snapshot_id=base_snapshot_id,
        start_date=args.start_date,
        end_date=args.end_date,
        activate=args.activate,
    )
    print(f"snapshot_id={publication.snapshot.snapshot_id}")
    for name, count in sorted(publication.row_counts.items()):
        print(f"{name}_rows={count}")
    print(f"activated={str(publication.activated).lower()}")
    print("strategy_gate_ready=false")
    print("broker_actions_allowed=false")
    return 0


def _current_snapshot(root: Path) -> str:
    value = json.loads((root / "current" / "data-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id = value.get("snapshot_id") if isinstance(value, dict) else None
    if not isinstance(snapshot_id, str):
        raise ValueError("当前 DataSnapshot 指针无效")
    return snapshot_id


@contextmanager
def publication_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("ETF 数据基础发布已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--base-snapshot-id")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2021, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, required=True)
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    with publication_lock(Path("var/control/etf-foundation.lock")):
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
