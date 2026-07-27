"""Explicit Tushare publication of the first bounded production DataSnapshot."""

from __future__ import annotations

import argparse
import asyncio
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
from astramind_mini.data.application import ProductionSnapshotService


async def run(provider_env_file: Path) -> int:
    settings = Settings()
    config = load_tushare_probe_config(settings, provider_env_file)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    service = ProductionSnapshotService(
        provider=TushareHttpClient(config),
        raw_store=FilesystemRawRecordStore(settings.data_dir),
        dataset_store=FilesystemDatasetStore(settings.data_dir),
        snapshot_store=FilesystemSnapshotStore(settings.data_dir),
        ledger=ledger,
        encoder=DuckDBParquetEncoder(),
    )
    publication = await service.publish()
    print(f"snapshot_id={publication.snapshot.snapshot_id}")
    print(f"as_of={publication.snapshot.as_of.isoformat()}")
    print(f"latest_trade_date={publication.latest_trade_date.isoformat()}")
    for name, count in sorted(publication.row_counts.items()):
        print(f"{name}: rows={count}")
    print("known_gaps=" + ",".join(publication.snapshot.known_gaps))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.provider_env_file))


if __name__ == "__main__":
    raise SystemExit(main())
