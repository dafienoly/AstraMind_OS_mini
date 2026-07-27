"""Publish historical name/ST and daily tradability projections."""

from __future__ import annotations

import argparse
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBHistoricalStatusProjector,
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
    discover_legacy_release,
)
from astramind_mini.data.application import StatusProjectionService


def run(args: argparse.Namespace) -> int:
    settings = Settings()
    release = discover_legacy_release(args.legacy_data_root, args.legacy_dataset_version)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    service = StatusProjectionService(
        data_root=settings.data_dir,
        dataset_store=FilesystemDatasetStore(settings.data_dir),
        snapshot_store=FilesystemSnapshotStore(settings.data_dir),
        ledger=ledger,
        projector=DuckDBHistoricalStatusProjector(),
    )
    publication = service.run(
        release=release,
        base_snapshot_id=args.base_snapshot_id,
        republish=args.republish,
    )
    print(f"snapshot_id={publication.snapshot.snapshot_id}")
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
            raise RuntimeError("历史状态投影已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-data-root", type=Path, required=True)
    parser.add_argument("--legacy-dataset-version", required=True)
    parser.add_argument("--base-snapshot-id", required=True)
    parser.add_argument("--republish", action="store_true")
    args = parser.parse_args()
    with import_lock(Path("var/control/data-backfill.lock")):
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
