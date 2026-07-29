"""Publish REQ-2026-0005 point-in-time tactical event datasets."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import httpx

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBEventDatasetCompactor,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    TushareHttpClient,
    load_tushare_probe_config,
)
from astramind_mini.data.application import TacticalEventBackfillService


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    config = load_tushare_probe_config(settings, args.provider_env_file)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        service = TacticalEventBackfillService(
            data_root=settings.data_dir,
            provider=TushareHttpClient(config, client),
            raw_store=FilesystemRawRecordStore(settings.data_dir),
            encoder=DuckDBParquetEncoder(),
            compactor=DuckDBEventDatasetCompactor(),
            dataset_store=FilesystemDatasetStore(settings.data_dir),
            snapshot_store=FilesystemSnapshotStore(settings.data_dir),
            ledger=ledger,
        )
        publication = await service.run(
            base_snapshot_id=args.base_snapshot_id,
            start_date=args.start_date,
            end_date=args.end_date,
            republish=args.republish,
        )
    print(f"snapshot_id={publication.snapshot.snapshot_id}")
    print(f"request_count={publication.request_count}")
    for manifest in publication.manifests:
        print(f"{manifest.dataset_name}_rows={manifest.row_count}")
    return 0


@contextmanager
def import_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("短线事件回填已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--base-snapshot-id", required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2023, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--republish", action="store_true")
    args = parser.parse_args()
    with import_lock(Path("var/control/tactical-event-backfill.lock")):
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
