from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import duckdb


def test_scheduler_dry_run_reads_versioned_calendar_without_provider(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[2]
    data_root = tmp_path / "data"
    dataset = data_root / "datasets" / "trade_calendar" / "abc"
    dataset.mkdir(parents=True)
    with duckdb.connect() as connection:
        connection.sql(
            """
            SELECT 'SSE' exchange, CAST(? AS DATE) calendar_date, true is_open
            """,
            params=[date(2026, 7, 28)],
        ).write_parquet(str(dataset / "trade_calendar.parquet"))
    (dataset / "manifest.json").write_text(
        json.dumps({"artifact_paths": ["trade_calendar.parquet"]}),
        encoding="utf-8",
    )
    current = data_root / "current"
    current.mkdir()
    (current / "trade_calendar.json").write_text(
        json.dumps(
            {
                "manifest_path": "datasets/trade_calendar/abc/manifest.json",
                "dataset_version": "sha256:" + "1" * 64,
            }
        ),
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["ASTRAMIND_DATA_DIR"] = str(data_root)
    environment["ASTRAMIND_LOCAL_OPS_DB_PATH"] = str(tmp_path / "local-ops.sqlite3")
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_daily_scheduler.py",
            "--provider-env-file",
            "/tmp/provider.env",
            "--at",
            "2026-07-28T16:35:00+08:00",
            "--dry-run",
        ],
        cwd=repository,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0
    assert "action=run" in completed.stdout
    assert "target_date=2026-07-28" in completed.stdout
    assert "broker_actions_allowed=false" in completed.stdout
