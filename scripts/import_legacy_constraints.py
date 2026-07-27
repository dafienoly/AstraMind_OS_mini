"""Import legacy daily metrics, price limits and suspension events."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    LegacyConstraintAnnualCompactor,
    TushareHttpClient,
    discover_legacy_release,
    load_tushare_probe_config,
)
from astramind_mini.data.application import ConstraintImportService


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    config = load_tushare_probe_config(settings, args.provider_env_file)
    release = discover_legacy_release(args.legacy_data_root, args.legacy_dataset_version)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    service = ConstraintImportService(
        data_root=settings.data_dir,
        provider=TushareHttpClient(config),
        raw_store=FilesystemRawRecordStore(settings.data_dir),
        dataset_store=FilesystemDatasetStore(settings.data_dir),
        snapshot_store=FilesystemSnapshotStore(settings.data_dir),
        ledger=ledger,
        compactor=LegacyConstraintAnnualCompactor(),
        encoder=DuckDBParquetEncoder(),
    )
    publication = await service.run(
        release=release,
        base_snapshot_id=args.base_snapshot_id,
        republish=args.republish,
    )
    print(f"snapshot_id={publication.snapshot.snapshot_id}")
    print(
        "fetched="
        + (",".join(f"{table}:{trade_date}" for table, trade_date in publication.fetched) or "none")
    )
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
            raise RuntimeError("历史导入已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--legacy-data-root", type=Path, required=True)
    parser.add_argument("--legacy-dataset-version", required=True)
    parser.add_argument("--base-snapshot-id", required=True)
    parser.add_argument("--republish", action="store_true")
    args = parser.parse_args()
    with import_lock(Path("var/control/data-backfill.lock")):
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
