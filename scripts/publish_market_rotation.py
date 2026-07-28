"""Build formal REQ-2026-0002 industry relative-rotation evidence."""

from __future__ import annotations

import argparse

from astramind_mini.config import Settings
from astramind_mini.market_regime.public import (
    FilesystemRotationStore,
    MarketRotationService,
    SnapshotRotationInput,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-snapshot-id", required=True)
    args = parser.parse_args()
    settings = Settings()
    publication = MarketRotationService(
        source=SnapshotRotationInput(settings.data_dir),
        store=FilesystemRotationStore(settings.rotation_data_dir),
    ).publish(args.data_snapshot_id)
    snapshot = publication.snapshot
    print(f"rotation_snapshot_id={snapshot.rotation_snapshot_id}")
    print(f"data_snapshot_id={snapshot.data_snapshot_id}")
    print(f"date_range={snapshot.date_range[0]}..{snapshot.date_range[1]}")
    print(f"industry_count={snapshot.industry_count}")
    print(f"point_count={len(snapshot.points)}")
    print(f"event_count={len(snapshot.events)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
