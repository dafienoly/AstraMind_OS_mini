import json
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import duckdb
import pytest

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.data.etf_foundation.history_backfill import (
    plan_etf_history_backfill,
    validate_etf_history_backfill_rows,
)


def test_backfill_plan_freezes_only_missing_listed_since_prefix(tmp_path: Path) -> None:
    snapshot_id = _fixture(tmp_path)

    plan = plan_etf_history_backfill(tmp_path, snapshot_id)

    assert plan.state == "backfill_required"
    assert plan.activation_allowed is False
    assert plan.rewrite_existing_version_allowed is False
    assert plan.v2_training_allowed is False
    assert plan.historical_performance_allowed is False
    assert len(plan.requests) == 1
    request = plan.requests[0]
    assert request.universe == ("510001.SH",)
    assert request.start_date == date(2018, 1, 2)
    assert request.end_date == date(2021, 1, 3)


def test_backfill_response_must_match_frozen_instrument_window_and_schema(
    tmp_path: Path,
) -> None:
    request = plan_etf_history_backfill(tmp_path, _fixture(tmp_path)).requests[0]
    valid = {
        "ts_code": "510001.SH",
        "trade_date": "20200102",
        "pre_close": 1.0,
        "open": 1.0,
        "high": 1.1,
        "low": 0.9,
        "close": 1.05,
        "change": 0.05,
        "pct_chg": 5.0,
        "vol": 1000,
        "amount": 10000,
    }

    validate_etf_history_backfill_rows(request, (valid,))
    with pytest.raises(ValueError, match="响应为空"):
        validate_etf_history_backfill_rows(request, ())
    with pytest.raises(ValueError, match="请求外证券"):
        validate_etf_history_backfill_rows(
            request,
            ({**valid, "ts_code": "510002.SH"},),
        )
    with pytest.raises(ValueError, match="日期窗口"):
        validate_etf_history_backfill_rows(
            request,
            ({**valid, "trade_date": "20210104"},),
        )


def _fixture(root: Path) -> str:
    master = _write(
        root,
        "etf_master",
        """
        SELECT '510001.SH' instrument_id, DATE '2018-01-02' list_date,
               TIMESTAMPTZ '2026-07-28 18:00:00+08' available_at
        """,
    )
    daily = _write(
        root,
        "etf_daily",
        """
        SELECT '510001.SH' instrument_id, CAST(day AS DATE) trade_date,
               TIMESTAMPTZ '2026-07-28 18:00:00+08' available_at
        FROM generate_series(DATE '2021-01-04', DATE '2026-07-28', INTERVAL 1 DAY) t(day)
        WHERE dayofweek(day) BETWEEN 1 AND 5
        """,
    )
    references = tuple(
        DatasetRef(
            dataset_name=name,
            dataset_version=version,
            schema_version="1.0.0",
            content_hash=version,
        )
        for name, version in (master, daily)
    )
    snapshot = DataSnapshot(
        snapshot_id="snapshot:sha256:" + "e" * 64,
        as_of=datetime(2026, 7, 29, 10, tzinfo=UTC),
        datasets=references,
        created_at=datetime(2026, 7, 29, 10, tzinfo=UTC),
        code_identity="etf-history-backfill-fixture",
    )
    directory = root / "snapshots" / ("e" * 64)
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(snapshot.model_dump_json(), encoding="utf-8")
    return snapshot.snapshot_id


def _write(root: Path, name: str, query: str) -> tuple[str, str]:
    digest = sha256(name.encode()).hexdigest()
    version = f"sha256:{digest}"
    directory = root / "datasets" / name / digest
    directory.mkdir(parents=True)
    artifact = directory / f"{name}.parquet"
    with duckdb.connect(":memory:") as connection:
        connection.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(artifact)])
    (directory / "manifest.json").write_text(
        json.dumps(
            {
                "dataset_version": version,
                "content_hash": version,
                "artifact_paths": [artifact.name],
            }
        ),
        encoding="utf-8",
    )
    return name, version
