"""Explicit real-provider benchmark; never part of the default test suite."""

from __future__ import annotations

import argparse
import asyncio
import platform
from dataclasses import asdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    MiniQMTBridgeClient,
    MiniQMTSourceAdapter,
    TushareHttpClient,
    TushareSourceAdapter,
    load_tushare_probe_config,
)
from astramind_mini.data.application.identity import canonical_json, content_hash
from astramind_mini.data.application.source_benchmark import benchmark_sources
from astramind_mini.data.application.source_quality import (
    QualityGateResult,
    ReplacementDecision,
    aggregate_quality_results,
    compare_provider_batches,
    replacement_decision,
)
from astramind_mini.data.application.source_route_policy import SourceRoutePolicyStore
from astramind_mini.data.contracts import (
    CanonicalDatasetRequest,
    DatasetSourceRoute,
    ProviderBenchmarkReport,
)
from astramind_mini.data.ports import BatchDataSourceAdapter

ROOT = Path(__file__).resolve().parents[1]
FIELDS = (
    "instrument_id",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "previous_close",
    "volume",
    "amount",
)
WIDE_INDICES = (
    "000001.SH",
    "399001.SZ",
    "399006.SZ",
    "000688.SH",
    "000300.SH",
    "000905.SH",
)
TUSHARE_BASELINE_RATE_LIMIT = 100
COMPARABLE_DATASETS = frozenset({"daily_market", "broad_index_daily"})
Gate = tuple[QualityGateResult, ReplacementDecision]
ScenarioGate = tuple[str, QualityGateResult]


async def run(args: argparse.Namespace) -> int:
    settings = Settings()
    if settings.miniqmt_xtquant_path is None or settings.miniqmt_quote_port is None:
        raise ValueError(
            "测速必须显式配置 ASTRAMIND_MINIQMT_XTQUANT_PATH 和 ASTRAMIND_MINIQMT_QUOTE_PORT"
        )
    config = load_tushare_probe_config(settings, args.provider_env_file)
    config = config.model_copy(update={"rate_limit_per_minute": TUSHARE_BASELINE_RATE_LIMIT})
    bridge = MiniQMTBridgeClient(
        runner=ROOT / "scripts/windows/miniqmt_data_bridge.py",
        xtquant_path=settings.miniqmt_xtquant_path,
        quote_port=settings.miniqmt_quote_port,
        python_command=settings.miniqmt_python or "py",
    )
    await bridge.start()
    miniqmt = MiniQMTSourceAdapter(bridge)
    as_of = datetime.now(UTC)
    requests, universe_count = _benchmark_requests(args, as_of)
    cache_preparation: dict[str, object] | None = None
    try:
        if args.prepare_miniqmt_cache:
            cache_preparation = await _prepare_miniqmt_cache(bridge, requests)
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tushare = TushareSourceAdapter(
                TushareHttpClient(config, client),
                allowed_datasets=COMPARABLE_DATASETS,
            )
            adapters: dict[str, BatchDataSourceAdapter] = {"miniqmt": miniqmt}
            if not args.performance_only:
                adapters["tushare"] = tushare
            report = await benchmark_sources(
                adapters=adapters,
                requests=requests,
                repetitions=args.repetitions,
                cache_state=args.cache_state,
                environment={
                    "platform": platform.platform(),
                    "python": platform.python_version(),
                    "miniqmt_client": bridge.provider_version,
                    "tushare_rate_limit_per_minute": str(config.rate_limit_per_minute),
                    "coverage_scope": args.coverage_scope,
                    "universe_count": str(universe_count),
                    "quick_relative_test": str(args.quick).lower(),
                    "cache_preparation": canonical_json(cache_preparation).decode()
                    if cache_preparation is not None
                    else "not_requested",
                },
            )
            scenario_gates: list[tuple[str, QualityGateResult]] = []
            for request in () if args.performance_only else requests:
                if request.dataset_name not in COMPARABLE_DATASETS:
                    continue
                candidate, reference = await miniqmt.fetch(request), await tushare.fetch(request)
                quality = compare_provider_batches(
                    dataset_name=request.dataset_name,
                    candidate=candidate,
                    reference=reference,
                    primary_key=("instrument_id", "trade_date"),
                    universe=frozenset(request.universe),
                )
                scenario_gates.append(
                    (
                        content_hash(request.model_dump(mode="json")),
                        quality,
                    )
                )
            gates: list[Gate] = []
            for dataset_name in sorted({quality.dataset_name for _, quality in scenario_gates}):
                quality = aggregate_quality_results(
                    dataset_name,
                    tuple(
                        item
                        for scenario_id, item in scenario_gates
                        if item.dataset_name == dataset_name
                    ),
                )
                decision = replacement_decision(
                    dataset_name=dataset_name,
                    quality=quality,
                    samples=report.samples,
                )
                gates.append((quality, decision))
    finally:
        await bridge.stop()
    report, output, gate_path = _write_reports(
        data_dir=settings.data_dir,
        report=report,
        gates=gates,
        scenario_gates=scenario_gates,
        coverage_scope=args.coverage_scope,
        universe_count=universe_count,
    )
    if args.activate:
        if args.performance_only:
            raise ValueError("仅性能报告不得激活生产路由")
        if args.quick:
            raise ValueError("快速相对测速报告不得直接激活生产路由")
        if args.coverage_scope != "production":
            raise ValueError("诊断测速报告不得激活生产路由")
        policy_hash = _activate_routes(settings.data_dir, report.benchmark_id, gates)
        print(f"route_policy={policy_hash}")
    print(f"benchmark_id={report.benchmark_id}")
    print(f"samples={len(report.samples)}")
    print(f"report={output}")
    print(f"quality_gates={gate_path}")
    print("broker_actions_allowed=false")
    return 0


def _write_reports(
    *,
    data_dir: Path,
    report: ProviderBenchmarkReport,
    gates: list[Gate],
    scenario_gates: list[ScenarioGate],
    coverage_scope: str,
    universe_count: int,
) -> tuple[ProviderBenchmarkReport, Path, Path]:
    output = data_dir / "benchmarks" / report.benchmark_id.rsplit(":", 1)[-1] / "report.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    conclusions = {
        decision.dataset_name: "replace" if decision.replace else ",".join(decision.reasons)
        for _, decision in gates
    }
    report = report.model_copy(update={"conclusions": conclusions})
    output.write_bytes(canonical_json(report.model_dump(mode="json")))
    gate_path = output.with_name("quality-gates.json")
    gate_path.write_bytes(
        canonical_json(
            {
                "benchmark_id": report.benchmark_id,
                "coverage_scope": coverage_scope,
                "universe_count": universe_count,
                "scenario_gates": [
                    {"scenario_id": scenario_id, "quality": asdict(quality)}
                    for scenario_id, quality in scenario_gates
                ],
                "gates": [
                    {"quality": asdict(quality), "decision": asdict(decision)}
                    for quality, decision in gates
                ],
            }
        )
    )
    return report, output, gate_path


def _activate_routes(data_dir: Path, benchmark_id: str, gates: list[Gate]) -> str:
    store = SourceRoutePolicyStore(data_dir)
    passing = {decision.dataset_name for _, decision in gates if decision.replace}
    routes = tuple(
        DatasetSourceRoute(
            **{
                **route.model_dump(),
                "providers": ("miniqmt", "tushare")
                if route.dataset_name in passing
                else route.providers,
                "quality_gate_version": benchmark_id
                if route.dataset_name in passing
                else route.quality_gate_version,
                "primary_key": ("instrument_id", "trade_date")
                if route.dataset_name in passing
                else route.primary_key,
            }
        )
        for route in store.load()
    )
    evidence = {
        route.dataset_name: (
            benchmark_id if route.dataset_name in passing else route.quality_gate_version
        )
        for route in routes
        if route.providers[0] == "miniqmt"
    }
    return store.publish(routes, gate_evidence=evidence, production_scope=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 7, 1))
    parser.add_argument("--end-date", type=date.fromisoformat, default=date(2026, 7, 28))
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--cache-state", choices=("cold", "warm"), default="warm")
    parser.add_argument(
        "--coverage-scope",
        choices=("diagnostic", "production"),
        default="diagnostic",
    )
    parser.add_argument("--universe-file", type=Path)
    parser.add_argument("--activate", action="store_true")
    parser.add_argument("--performance-only", action="store_true")
    parser.add_argument("--prepare-miniqmt-cache", action="store_true")
    parser.add_argument("--quick", action="store_true")
    return asyncio.run(run(parser.parse_args()))


async def _prepare_miniqmt_cache(
    bridge: MiniQMTBridgeClient,
    requests: tuple[CanonicalDatasetRequest, ...],
) -> dict[str, object]:
    daily = tuple(request for request in requests if request.dataset_name == "daily_market")
    if not daily:
        raise ValueError("没有可用于缓存准备的股票日线场景")
    request = max(
        daily,
        key=lambda item: (
            len(item.universe),
            (item.end_date - item.start_date).days
            if item.start_date is not None and item.end_date is not None
            else 0,
        ),
    )
    if request.start_date is None or request.end_date is None:
        raise ValueError("缓存准备场景必须包含日期范围")
    started = datetime.now(UTC)
    batches: list[dict[str, object]] = []
    batch_size = MiniQMTSourceAdapter.market_batch_size
    for offset in range(0, len(request.universe), batch_size):
        universe = request.universe[offset : offset + batch_size]
        result = await bridge.request(
            "prepare_history_cache",
            timeout_seconds=180,
            universe=universe,
            period="1d",
            start_time=request.start_date.strftime("%Y%m%d"),
            end_time=request.end_date.strftime("%Y%m%d"),
        )
        batches.append(result)
        print(
            "cache_preparation="
            f"{min(offset + len(universe), len(request.universe))}/{len(request.universe)}",
            flush=True,
        )
    ended = datetime.now(UTC)
    return {
        "native_interface": "download_history_data2-chunked",
        "instrument_count": len(request.universe),
        "batch_size": batch_size,
        "batch_count": len(batches),
        "provider_elapsed_ms": sum(_numeric_value(batch.get("elapsed_ms")) for batch in batches),
        "elapsed_ms": (ended - started).total_seconds() * 1000,
        "started_at": started.isoformat(),
        "ended_at": ended.isoformat(),
    }


def _numeric_value(value: object) -> float:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else 0.0


def _benchmark_requests(
    args: argparse.Namespace,
    as_of: datetime,
) -> tuple[tuple[CanonicalDatasetRequest, ...], int]:
    if args.coverage_scope == "diagnostic":
        return _diagnostic_requests(args, as_of), 1
    universe = _production_universe(args)
    if args.quick:
        return _quick_requests(args, as_of, universe), len(universe)
    if args.repetitions < 5:
        raise ValueError("生产范围场景至少重复 5 次")
    return _full_production_requests(args, as_of, universe), len(universe)


def _diagnostic_requests(
    args: argparse.Namespace,
    as_of: datetime,
) -> tuple[CanonicalDatasetRequest, ...]:
    extended_start = args.end_date - timedelta(days=365 * 5)
    return (
        CanonicalDatasetRequest(
            dataset_name="daily_market",
            as_of=as_of,
            start_date=args.start_date,
            end_date=args.end_date,
            universe=("600519.SH",),
            fields=FIELDS,
            frequency="1d",
        ),
        CanonicalDatasetRequest(
            dataset_name="broad_index_daily",
            as_of=as_of,
            start_date=args.start_date,
            end_date=args.end_date,
            universe=("000300.SH",),
            fields=FIELDS,
            frequency="1d",
        ),
        CanonicalDatasetRequest(
            dataset_name="minute_market",
            as_of=as_of,
            start_date=args.end_date,
            end_date=args.end_date,
            universe=("600519.SH",),
            frequency="1m",
        ),
        CanonicalDatasetRequest(
            dataset_name="instrument_snapshot",
            as_of=as_of,
            universe=("600519.SH",),
        ),
        CanonicalDatasetRequest(
            dataset_name="index_constituent_weight_current",
            as_of=as_of,
            universe=("000300.SH",),
        ),
        CanonicalDatasetRequest(
            dataset_name="sector_catalog_current",
            as_of=as_of,
        ),
        CanonicalDatasetRequest(
            dataset_name="sector_membership_current",
            as_of=as_of,
            filters={"sectors": ("沪深300", "上证50", "中证500")},
        ),
        *(
            CanonicalDatasetRequest(
                dataset_name=dataset_name,
                as_of=as_of,
                start_date=extended_start,
                end_date=args.end_date,
                universe=("600519.SH",),
                filters={"table": "Balance"} if dataset_name == "financial_statement" else {},
            )
            for dataset_name in (
                "financial_statement",
                "shareholder_count",
                "top10_holder",
                "top10_float_holder",
            )
        ),
    )


def _production_universe(args: argparse.Namespace) -> tuple[str, ...]:
    if args.universe_file is None or not args.universe_file.is_file():
        raise ValueError("生产范围测速必须提供 --universe-file")
    universe = tuple(
        line.strip()
        for line in args.universe_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if len(universe) < 1000 or len(universe) != len(set(universe)):
        raise ValueError("生产范围证券池必须至少 1000 只且不得重复")
    return universe


def _quick_requests(
    args: argparse.Namespace,
    as_of: datetime,
    universe: tuple[str, ...],
) -> tuple[CanonicalDatasetRequest, ...]:
    if args.repetitions < 3:
        raise ValueError("快速相对测速至少重复 3 次")
    comparison_requests = (
        CanonicalDatasetRequest(
            dataset_name="daily_market",
            as_of=as_of,
            start_date=args.end_date,
            end_date=args.end_date,
            universe=universe,
            fields=FIELDS,
            frequency="1d",
        ),
        CanonicalDatasetRequest(
            dataset_name="broad_index_daily",
            as_of=as_of,
            start_date=args.end_date - timedelta(days=31),
            end_date=args.end_date,
            universe=WIDE_INDICES,
            fields=FIELDS,
            frequency="1d",
        ),
    )
    if not args.performance_only:
        return comparison_requests
    history_request = CanonicalDatasetRequest(
        dataset_name="daily_market",
        as_of=as_of,
        start_date=args.end_date - timedelta(days=31),
        end_date=args.end_date,
        universe=universe[:500],
        fields=FIELDS,
        frequency="1d",
    )
    return (comparison_requests[0], history_request, comparison_requests[1])


def _full_production_requests(
    args: argparse.Namespace,
    as_of: datetime,
    universe: tuple[str, ...],
) -> tuple[CanonicalDatasetRequest, ...]:
    periods = ((1, 0), (20, 31), (250, 370))
    sizes = (1, 50, 500, len(universe))
    requests = [
        CanonicalDatasetRequest(
            dataset_name="daily_market",
            as_of=as_of,
            start_date=args.end_date - timedelta(days=calendar_days),
            end_date=args.end_date,
            universe=universe[:size],
            fields=FIELDS,
            frequency="1d",
        )
        for _, calendar_days in periods
        for size in sizes
    ]
    requests.extend(
        CanonicalDatasetRequest(
            dataset_name="broad_index_daily",
            as_of=as_of,
            start_date=args.end_date - timedelta(days=calendar_days),
            end_date=args.end_date,
            universe=WIDE_INDICES,
            fields=FIELDS,
            frequency="1d",
        )
        for _, calendar_days in periods
    )
    return tuple(requests)


if __name__ == "__main__":
    raise SystemExit(main())
