from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters.market_session_context import SnapshotMarketSessionContext
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.contracts.provider import DatasetManifest


def test_context_uses_calendar_and_common_completed_market_date(tmp_path: Path) -> None:
    references = []
    calendar_version = _manifest(
        tmp_path,
        name="trade_calendar",
        end=date(2026, 7, 30),
        artifact="calendar.parquet",
    )
    calendar_path = (
        tmp_path
        / "datasets"
        / "trade_calendar"
        / calendar_version.removeprefix("sha256:")
        / "calendar.parquet"
    )
    with duckdb.connect(":memory:") as connection:
        connection.execute(
            f"""
            COPY (
              SELECT * FROM (VALUES
                (DATE '2026-07-28', 'SSE', false),
                (DATE '2026-07-29', 'SSE', true),
                (DATE '2026-07-30', 'SSE', true)
              ) AS calendar(calendar_date, exchange, is_open)
            ) TO '{calendar_path.as_posix()}' (FORMAT PARQUET)
            """
        )
    references.append(_reference("trade_calendar", calendar_version))
    for name, end in (
        ("broad_index_daily", date(2026, 7, 30)),
        ("daily_market", date(2026, 7, 29)),
        ("industry_index_daily", date(2026, 7, 30)),
    ):
        version = _manifest(tmp_path, name=name, end=end, artifact="placeholder.parquet")
        references.append(_reference(name, version))
    snapshot_digest = content_hash({"snapshot": "market-session"}).removeprefix("sha256:")
    snapshot_id = f"snapshot:sha256:{snapshot_digest}"
    snapshot_path = tmp_path / "snapshots" / snapshot_digest / "manifest.json"
    snapshot_path.parent.mkdir(parents=True)
    snapshot_path.write_text(
        json.dumps({"snapshot_id": snapshot_id, "datasets": references}),
        encoding="utf-8",
    )
    current = tmp_path / "current"
    current.mkdir()
    (current / "data-snapshot.json").write_text(
        json.dumps({"snapshot_id": snapshot_id}),
        encoding="utf-8",
    )

    context = SnapshotMarketSessionContext(tmp_path).read(today=date(2026, 7, 30))

    assert context.open_dates == (date(2026, 7, 29), date(2026, 7, 30))
    assert context.latest_completed_trade_date == date(2026, 7, 29)


def _manifest(tmp_path: Path, *, name: str, end: date, artifact: str) -> str:
    version = content_hash({"dataset": name})
    manifest = DatasetManifest(
        dataset_name=name,
        dataset_version=version,
        schema_version="1.0.0",
        provider="fixture",
        source_endpoint="fixture",
        request_identity=content_hash({"request": name}),
        retrieved_at=datetime(2026, 7, 30, tzinfo=UTC),
        market_timezone="Asia/Shanghai",
        date_range=(date(2026, 7, 1), end),
        universe=("SSE",),
        primary_key=("date",),
        availability_rule="fixture",
        units=("fixture",),
        content_hash=content_hash({"content": name}),
        row_count=1,
        artifact_paths=(artifact,),
        publish_status="complete",
    )
    directory = tmp_path / "datasets" / name / version.removeprefix("sha256:")
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")
    return version


def _reference(name: str, version: str) -> dict[str, str]:
    return {
        "dataset_name": name,
        "dataset_version": version,
        "content_hash": content_hash({"content": name}),
    }
