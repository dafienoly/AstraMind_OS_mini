from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import duckdb

from astramind_mini.data.public import SnapshotShadowMarketReader

SNAPSHOT_ID = "snapshot:sha256:" + "a" * 64


def test_reader_uses_only_exact_snapshot_manifests(tmp_path: Path) -> None:
    datasets = {
        "daily_market": (
            "sha256:" + "b" * 64,
            """
            SELECT 'legacy' provider, 'daily' source_endpoint,
                   TIMESTAMPTZ '2026-07-29 10:00:00+00' retrieved_at,
                   TIMESTAMPTZ '2026-07-29 10:00:00+00' available_at,
                   '1' schema_version, 'sha256:x' source_record_hash,
                   '000001.SZ' instrument_id, DATE '2026-07-29' trade_date,
                   10.0 AS "open", 10.3 AS high, 9.9 AS low, 10.2 AS "close",
                   9.8 AS previous_close,
                   0.4 change, 4.0 percent_change, 100000 volume_lots,
                   2000 amount_thousand_cny
            """,
        ),
        "daily_tradability": (
            "sha256:" + "c" * 64,
            """
            SELECT 'derived' provider, 'tradability' source_endpoint,
                   TIMESTAMPTZ '2026-07-29 10:00:00+00' retrieved_at,
                   TIMESTAMPTZ '2026-07-29 10:00:00+00' available_at,
                   '1' schema_version, 'sha256:y' source_record_hash,
                   '000001.SZ' instrument_id, DATE '2026-07-29' trade_date,
                   'tradable' buy_state, 'tradable' sell_state, true has_daily_bar
            """,
        ),
        "trade_calendar": (
            "sha256:" + "d" * 64,
            """
            SELECT 'tushare' provider, 'trade_cal' source_endpoint,
                   TIMESTAMPTZ '2026-07-28 10:00:00+00' retrieved_at,
                   TIMESTAMPTZ '2026-07-28 10:00:00+00' available_at,
                   '1' schema_version, 'sha256:z' source_record_hash,
                   'SSE' exchange, DATE '2026-07-29' calendar_date, true is_open,
                   DATE '2026-07-28' previous_trade_date
            """,
        ),
    }
    references = []
    with duckdb.connect(":memory:") as connection:
        for name, (version, query) in datasets.items():
            digest = version.removeprefix("sha256:")
            directory = tmp_path / "datasets" / name / digest
            directory.mkdir(parents=True)
            parquet = directory / "data.parquet"
            connection.execute(f"COPY ({query}) TO ? (FORMAT PARQUET)", [str(parquet)])
            (directory / "manifest.json").write_text(
                json.dumps(
                    {
                        "dataset_name": name,
                        "dataset_version": version,
                        "artifact_paths": ["data.parquet"],
                    }
                ),
                encoding="utf-8",
            )
            references.append({"dataset_name": name, "dataset_version": version})
    snapshot = tmp_path / "snapshots" / SNAPSHOT_ID.rsplit(":", 1)[-1]
    snapshot.mkdir(parents=True)
    (snapshot / "manifest.json").write_text(
        json.dumps({"snapshot_id": SNAPSHOT_ID, "datasets": references}),
        encoding="utf-8",
    )

    reader = SnapshotShadowMarketReader(tmp_path, SNAPSHOT_ID)
    dates = reader.trading_dates(
        start_date=date(2026, 7, 29),
        end_date=date(2026, 7, 29),
    )
    observations = reader.observations(instruments=("000001.SZ",), trade_date=dates[0])

    assert dates == (date(2026, 7, 29),)
    assert observations[0].data_snapshot_id == SNAPSHOT_ID
    assert observations[0].open_price == 10.0
    assert observations[0].amount_cny == 2_000_000
    assert observations[0].buy_state == "tradable"
