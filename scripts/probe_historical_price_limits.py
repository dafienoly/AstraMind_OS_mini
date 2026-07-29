"""Probe every 2000-2006 trading session before authorizing a price-limit backfill."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import httpx

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DuckDBParquetEncoder,
    FilesystemRawRecordStore,
    TushareHttpClient,
    load_tushare_probe_config,
)
from astramind_mini.data.application.historical_price_limit_probe import (
    HistoricalPriceLimitProbeService,
)


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    config = load_tushare_probe_config(settings, args.provider_env_file)
    async with httpx.AsyncClient(follow_redirects=True) as client:
        service = HistoricalPriceLimitProbeService(
            data_root=settings.data_dir,
            provider=TushareHttpClient(config, client),
            raw_store=FilesystemRawRecordStore(settings.data_dir),
            encoder=DuckDBParquetEncoder(),
        )
        result = await service.run(
            base_snapshot_id=args.base_snapshot_id or _current_snapshot_id(settings.data_dir),
            start_date=args.start_date,
            end_date=args.end_date,
        )
    print(f"state={result.state}")
    print(f"expected_sessions={result.expected_sessions}")
    print(f"observed_sessions={result.observed_sessions}")
    print(f"empty_sessions={len(result.empty_sessions)}")
    print(f"artifact_path={result.artifact_path}")
    print("publish_price_limit=false")
    print("broker_actions_allowed=false")
    return 0


def _current_snapshot_id(root: Path) -> str:
    value = json.loads((root / "current" / "data-snapshot.json").read_text(encoding="utf-8"))
    snapshot_id = value.get("snapshot_id") if isinstance(value, dict) else None
    if not isinstance(snapshot_id, str):
        raise ValueError("当前 DataSnapshot 指针无效")
    return snapshot_id


@contextmanager
def probe_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("历史涨跌停探测已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--base-snapshot-id")
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2000, 1, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2006, 12, 31))
    args = parser.parse_args()
    with probe_lock(Path("var/control/historical-price-limit-probe.lock")):
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
