"""Manifest construction for WP-0002B-H4."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from ..contracts import DatasetManifest
from ..ports import LegacyMarketRelease
from .datasets import build_dataset_manifest_from_hashes
from .historical_publication import FileArtifacts
from .identity import canonical_json, file_hash
from .state_files import write_bytes_atomic


def build_corporate_action_manifests(
    *,
    base: dict[str, DatasetManifest],
    release: LegacyMarketRelease,
    import_id: str,
    action_path: Path,
    action_stats: dict[str, int],
    yearly: dict[int, dict[str, object]],
    staging: Path,
    finished_at: datetime,
) -> tuple[tuple[DatasetManifest, ...], FileArtifacts]:
    artifacts: FileArtifacts = {
        "corporate_action": {"corporate-action.parquet": (action_path, file_hash(action_path))},
        "adjusted_market": {},
    }
    for year, item in sorted(yearly.items()):
        path = Path(str(item["path"]))
        artifacts["adjusted_market"][f"adjusted-market-{year}.parquet"] = (
            path,
            str(item["hash"]),
        )
    totals = _totals(yearly)
    coverage = {
        "corporate_action": action_stats,
        "annual": yearly,
        "totals": totals,
        "source_dataset_version": release.dataset_version,
        "price_policy": {
            "execution": "raw_ohlc_only",
            "canonical_research": "reported_pct_chg_compounded_index",
            "factor_compatibility": "snapshot_qfq_and_hfq",
        },
    }
    for name in artifacts:
        path = staging / f"{name}-coverage.json"
        write_bytes_atomic(path, canonical_json({"dataset_name": name, **coverage}))
        artifacts[name]["coverage.json"] = (path, file_hash(path))
    date_range = base["daily_market"].date_range
    universe = base["security_master"].universe
    return (
        _manifest(
            name="corporate_action",
            provider="tushare",
            endpoint="legacy-astramind-silver/dividend",
            import_id=import_id,
            finished_at=finished_at,
            date_range=(date(1998, 3, 23), date_range[1]),
            universe=universe,
            primary_key=("provider_record_hash",),
            availability_rule="announced_on 18:00 Asia/Shanghai; retrieval time when unknown",
            row_count=action_stats["rows"],
            artifacts=artifacts,
            gaps=_action_gaps(action_stats),
            units=(
                "stock_dividend:share_per_share",
                "cash_dividend:CNY_per_share",
                "base_shares:ten_thousand_shares",
            ),
        ),
        _manifest(
            name="adjusted_market",
            provider="derived",
            endpoint="snapshot-adjusted-market",
            import_id=import_id,
            finished_at=finished_at,
            date_range=date_range,
            universe=universe,
            primary_key=("instrument_id", "trade_date"),
            availability_rule="trade_date 18:00 Asia/Shanghai",
            row_count=totals["rows"],
            artifacts=artifacts,
            gaps=_adjusted_gaps(totals),
            units=("price:CNY", "research_price:index", "return:decimal"),
        ),
    ), artifacts


def _manifest(
    *,
    name: str,
    provider: str,
    endpoint: str,
    import_id: str,
    finished_at: datetime,
    date_range: tuple[date, date],
    universe: tuple[str, ...],
    primary_key: tuple[str, ...],
    availability_rule: str,
    row_count: int,
    artifacts: FileArtifacts,
    gaps: tuple[str, ...],
    units: tuple[str, ...],
) -> DatasetManifest:
    return build_dataset_manifest_from_hashes(
        dataset_name=name,
        schema_version="1.0.0",
        provider=provider,
        source_endpoint=endpoint,
        request_identity=import_id,
        retrieved_at=finished_at,
        market_timezone="Asia/Shanghai",
        date_range=date_range,
        universe=universe,
        primary_key=primary_key,
        availability_rule=availability_rule,
        units=units,
        row_count=row_count,
        artifact_hashes={key: value[1] for key, value in artifacts[name].items()},
        known_gaps=gaps,
    )


def _totals(yearly: dict[int, dict[str, object]]) -> dict[str, int]:
    keys = (
        "rows",
        "factor_change_rows",
        "factor_changes_with_action",
        "factor_return_error_over_1bp",
        "invalid_research_price_rows",
    )
    return {key: sum(_integer(item[key]) for item in yearly.values()) for key in keys}


def _action_gaps(stats: dict[str, int]) -> tuple[str, ...]:
    gaps = [
        "legacy_raw_payloads_external",
        "rights_issues_and_other_actions_not_in_source",
    ]
    if stats["unknown_availability_rows"]:
        gaps.append("corporate_action_rows_with_unknown_announcement_date")
    return tuple(gaps)


def _adjusted_gaps(totals: dict[str, int]) -> tuple[str, ...]:
    gaps = ["factor_compatibility_prices_are_snapshot_relative"]
    unexplained = totals["factor_change_rows"] - totals["factor_changes_with_action"]
    if unexplained:
        gaps.append("factor_changes_without_implemented_dividend_evidence")
    if totals["factor_return_error_over_1bp"]:
        gaps.append("factor_return_differs_from_reported_return")
    return tuple(gaps)


def _integer(value: object) -> int:
    if not isinstance(value, int):
        raise ValueError("年度复权统计不是整数")
    return value


__all__ = ["build_corporate_action_manifests"]
