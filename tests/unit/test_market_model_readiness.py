from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from astramind_mini.data.adapters import (
    FilesystemDatasetStore,
    FilesystemSnapshotStore,
)
from astramind_mini.data.application.datasets import (
    DataSnapshotBuilder,
    build_dataset_manifest,
)
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts import DatasetManifest
from astramind_mini.strategy_research.adapters import MarketModelReadinessReader

NOW = datetime(2026, 7, 29, 10, tzinfo=UTC)


def test_readiness_distinguishes_development_from_supportive_evidence(
    tmp_path: Path,
) -> None:
    manifests = tuple(
        _manifest(
            tmp_path,
            name,
            gaps=(
                ("historical_membership_publication_time_unavailable",)
                if name == "industry_membership"
                else ("historical_mapping_availability_unknown",)
                if name == "etf_official_benchmark"
                else ()
            ),
        )
        for name in (
            "industry_index_daily",
            "official_index_daily",
            "industry_membership",
            "daily_market",
            "daily_basic",
            "etf_daily",
            "etf_nav",
            "etf_official_benchmark",
        )
    )
    snapshot = DataSnapshotBuilder().build(
        manifests=manifests,
        as_of=NOW,
        created_at=NOW,
        code_identity="test",
    )
    snapshots = FilesystemSnapshotStore(tmp_path)
    path = snapshots.publish(snapshot)
    snapshots.activate(snapshot, path)
    for day in (date(2026, 7, 28), date(2026, 7, 29)):
        (tmp_path / "realtime" / "miniqmt" / "etf-spread" / f"market-date={day}").mkdir(
            parents=True
        )

    report = MarketModelReadinessReader(tmp_path).current()
    heat = next(item for item in report.models if item.model_family == "industry_heat")
    lifecycle = next(item for item in report.models if item.model_family == "industry_lifecycle")
    etf = next(item for item in report.models if item.model_family == "etf_rotation")

    assert heat.development_ready
    assert not heat.supportive_evidence_ready
    assert not lifecycle.development_ready
    assert "historical_membership_not_then_known" in lifecycle.reason_codes
    assert "l1_spread_sessions:2/60" in etf.reason_codes
    assert report.broker_actions_allowed is False


def _manifest(
    root: Path,
    name: str,
    *,
    gaps: tuple[str, ...],
) -> DatasetManifest:
    artifacts = {f"{name}.bin": name.encode()}
    manifest = build_dataset_manifest(
        dataset_name=name,
        schema_version="test-v1",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash(name),
        retrieved_at=NOW,
        market_timezone="Asia/Shanghai",
        date_range=(date(2010, 1, 1), date(2026, 7, 29)),
        universe=(),
        primary_key=("id",),
        availability_rule="fixture",
        units=(),
        row_count=1,
        artifacts=artifacts,
        known_gaps=gaps,
    )
    FilesystemDatasetStore(root).publish(manifest, artifacts)
    return manifest
