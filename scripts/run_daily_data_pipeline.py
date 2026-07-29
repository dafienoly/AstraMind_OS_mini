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
    MiniQMTBridgeClient,
    MiniQMTSourceAdapter,
    RoutedHistoricalProvider,
    TushareHttpClient,
    TushareSourceAdapter,
    load_tushare_probe_config,
)
from astramind_mini.data.application.daily_pipeline import DailyIndustryPipeline
from astramind_mini.data.application.daily_pipeline_inputs import DailyDatasetExtensions
from astramind_mini.data.application.source_route_policy import SourceRoutePolicyStore
from astramind_mini.data.application.source_router import DatasetSourceRouter
from astramind_mini.data.etf_foundation import EtfFoundationService
from astramind_mini.data.ports import BatchDataSourceAdapter
from astramind_mini.market_regime.adapters import FilesystemRotationStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path)
    parser.add_argument("--base-snapshot-id")
    parser.add_argument("--target-date", type=date.fromisoformat)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--recover", action="store_true")
    parser.add_argument(
        "--market-only",
        action="store_true",
        help="只更新交易日历、行业与宽基市场数据，不刷新股票研究和事件输入",
    )
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
    raw_store = FilesystemRawRecordStore(settings.data_dir)
    route_store = SourceRoutePolicyStore(settings.data_dir)
    routes = route_store.load()
    bridge = None
    async with httpx.AsyncClient(follow_redirects=True) as client:
        tushare_client = TushareHttpClient(config, client)
        adapters: dict[str, BatchDataSourceAdapter] = {
            "tushare": TushareSourceAdapter(tushare_client),
        }
        if any("miniqmt" in route.providers for route in routes):
            if settings.miniqmt_xtquant_path is None or settings.miniqmt_quote_port is None:
                raise ValueError("已启用 MiniQMT 数据路由，但未固定 XtQuant 路径和行情端口")
            bridge = MiniQMTBridgeClient(
                runner=Path("scripts/windows/miniqmt_data_bridge.py"),
                xtquant_path=settings.miniqmt_xtquant_path,
                quote_port=settings.miniqmt_quote_port,
                python_command=settings.miniqmt_python or "py",
            )
            adapters["miniqmt"] = MiniQMTSourceAdapter(bridge)
        routed_provider = RoutedHistoricalProvider(
            DatasetSourceRouter(
                adapters=adapters,
                routes=routes,
                raw_store=raw_store,
            )
        )
        dataset_store = FilesystemDatasetStore(settings.data_dir)
        snapshot_store = FilesystemSnapshotStore(settings.data_dir)
        encoder = DuckDBParquetEncoder()
        etf_service = EtfFoundationService(
            data_root=settings.data_dir,
            provider=tushare_client,
            raw_store=raw_store,
            encoder=encoder,
            dataset_store=dataset_store,
            snapshot_store=snapshot_store,
            ledger=ledger,
        )

        async def prepare_etf_extensions(
            base_id: str,
            target_date: date,
        ) -> DailyDatasetExtensions:
            prepared = await etf_service.prepare(
                base_snapshot_id=base_id,
                start_date=date(2021, 1, 1),
                end_date=target_date,
            )
            return DailyDatasetExtensions(
                manifests={item.dataset_name: item for item in prepared.manifests},
                paths=prepared.manifest_paths,
                retrieved_at=prepared.retrieved_at,
                known_gaps=prepared.known_gaps,
                resolved_gaps=prepared.resolved_gaps,
            )

        service = DailyIndustryPipeline(
            data_root=settings.data_dir,
            rotation_root=settings.rotation_data_dir,
            provider=routed_provider,
            encoder=encoder,
            raw_store=raw_store,
            dataset_store=dataset_store,
            snapshot_store=snapshot_store,
            rotation_store=FilesystemRotationStore(settings.rotation_data_dir),
            control_store=control,
            ledger=ledger,
            prepare_extensions=prepare_etf_extensions,
        )
        try:
            publication = await service.run(
                base_snapshot_id=base_snapshot_id,
                target_date=args.target_date,
                started_at=datetime.now(SHANGHAI),
                recover=args.recover,
                include_research_inputs=not args.market_only,
                include_event_inputs=not args.market_only,
            )
            for evidence in routed_provider.selection_evidence:
                route_store.append_selection(evidence)
        finally:
            if bridge is not None:
                await bridge.stop()
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
