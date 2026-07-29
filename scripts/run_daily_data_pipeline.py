"""Run or inspect the explicit WP-0025 local daily data pipeline."""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    DailyPipelineStore,
    DataControlLedger,
    DuckDBParquetEncoder,
    FilesystemDatasetStore,
    FilesystemRawRecordStore,
    FilesystemSnapshotStore,
    TushareHttpClient,
    load_tushare_probe_config,
)
from astramind_mini.data.application.daily_pipeline import DailyIndustryPipeline
from astramind_mini.market_regime.adapters import FilesystemRotationStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--base-snapshot-id")
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--status", action="store_true")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    control = DailyPipelineStore(settings.control_db_path, settings.data_dir)
    control.migrate()
    if args.status:
        status = control.latest_status()
        if status is None:
            print("state=waiting_data")
            print("broker_actions_allowed=false")
            return 0
        _print_status(status.model_dump(mode="json"))
        return 0
    if args.provider_env_file is None or args.target_date is None:
        raise ValueError("运行增量必须提供 --provider-env-file 和 --target-date")
    base_snapshot_id = args.base_snapshot_id or _current_snapshot_id(settings.data_dir)
    config = load_tushare_probe_config(settings, args.provider_env_file)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    async with httpx.AsyncClient(follow_redirects=True) as client:
        service = DailyIndustryPipeline(
            data_root=settings.data_dir,
            rotation_root=settings.rotation_data_dir,
            provider=TushareHttpClient(config, client),
            encoder=DuckDBParquetEncoder(),
            raw_store=FilesystemRawRecordStore(settings.data_dir),
            dataset_store=FilesystemDatasetStore(settings.data_dir),
            snapshot_store=FilesystemSnapshotStore(settings.data_dir),
            rotation_store=FilesystemRotationStore(settings.rotation_data_dir),
            control_store=control,
            ledger=ledger,
        )
        publication = await service.run(
            base_snapshot_id=base_snapshot_id,
            target_date=args.target_date,
            started_at=datetime.now(SHANGHAI),
        )
    _print_status(publication.status.model_dump(mode="json"))
    if publication.commit:
        print(f"commit_id={publication.commit.commit_id}")
    return 0


def _current_snapshot_id(root: Path) -> str:
    value = json.loads((root / "current" / "data-snapshot.json").read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("当前 DataSnapshot 指针无效")
    snapshot_id = value.get("snapshot_id")
    if not isinstance(snapshot_id, str):
        raise ValueError("当前 DataSnapshot 指针无效")
    return snapshot_id


def _print_status(value: dict[str, object]) -> None:
    for field in (
        "state",
        "target_date",
        "data_snapshot_id",
        "rotation_snapshot_id",
        "observed_l1_count",
        "observed_l2_count",
        "recovery_action",
    ):
        if value.get(field) is not None:
            print(f"{field}={value[field]}")
    blockers = value.get("blocker_codes")
    if isinstance(blockers, (list, tuple)) and blockers:
        print("blocker_codes=" + ",".join(str(item) for item in blockers))
    print("broker_actions_allowed=false")


@contextmanager
def pipeline_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("日度数据管线已有进程在运行") from error
        yield


def main() -> int:
    args = parse_args()
    with pipeline_lock(Path("var/control/daily-data-pipeline.lock")):
        return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
