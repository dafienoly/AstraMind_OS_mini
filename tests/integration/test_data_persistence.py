from datetime import UTC, date, datetime
from pathlib import Path

import duckdb

from astramind_mini.data.adapters import (
    DataControlLedger,
    DuckDBParquetEncoder,
    DuckDBSnapshotQuery,
    FilesystemDatasetStore,
)
from astramind_mini.data.application import (
    build_dataset_manifest,
    build_dataset_manifest_from_hashes,
    content_hash,
    file_hash,
)
from astramind_mini.data.application.dataset_schemas import SUSPENSION_EVENT_COLUMNS


def test_sqlite_migrations_restart_and_versioned_duckdb_query(tmp_path: Path) -> None:
    database = tmp_path / "control/data.db"
    ledger = DataControlLedger(database)
    ledger.migrate()
    ledger.migrate()
    assert ledger.journal_mode() == "wal"
    with duckdb.connect(":memory:") as connection:
        parquet = tmp_path / "staging.parquet"
        connection.execute(
            "COPY (SELECT '000001.SZ' AS instrument_id, 10.5 AS close) TO ? (FORMAT PARQUET)",
            [str(parquet)],
        )
    artifacts = {"data.parquet": parquet.read_bytes()}
    manifest = build_dataset_manifest(
        dataset_name="synthetic_daily",
        schema_version="1.0.0",
        provider="synthetic",
        source_endpoint="fixture",
        request_identity=content_hash({"fixture": 1}),
        retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
        market_timezone="Asia/Shanghai",
        date_range=(date(2026, 1, 15), date(2026, 1, 15)),
        universe=("000001.SZ",),
        primary_key=("instrument_id",),
        availability_rule="fixture",
        units=("close:CNY",),
        row_count=1,
        artifacts=artifacts,
    )
    manifest_path = FilesystemDatasetStore(tmp_path).publish(manifest, artifacts)
    ledger.record_dataset(manifest, manifest_path)
    query = DuckDBSnapshotQuery(tmp_path)

    rows = query.query_parquet(
        manifest,
        "data.parquet",
        "SELECT instrument_id, close FROM {dataset}",
    )

    assert rows == [("000001.SZ", 10.5)]


def test_file_backed_partition_publication_and_exact_set_query(tmp_path: Path) -> None:
    parts = {}
    for year, close in ((2000, 10.0), (2001, 11.0)):
        path = tmp_path / f"stage-{year}.parquet"
        with duckdb.connect(":memory:") as connection:
            output = str(path).replace("'", "''")
            connection.execute(
                f"COPY (SELECT ? AS instrument_id, ? AS close) TO '{output}' (FORMAT PARQUET)",
                ["000001.SZ", close],
            )
        parts[f"daily-market-{year}.parquet"] = (path, file_hash(path))
    manifest = build_dataset_manifest_from_hashes(
        dataset_name="daily_market",
        schema_version="1.1.0",
        provider="synthetic",
        source_endpoint="fixture",
        request_identity=content_hash({"parts": 2}),
        retrieved_at=datetime(2026, 1, 15, tzinfo=UTC),
        market_timezone="Asia/Shanghai",
        date_range=(date(2000, 1, 1), date(2001, 12, 31)),
        universe=("000001.SZ",),
        primary_key=("instrument_id",),
        availability_rule="fixture",
        units=("close:CNY",),
        row_count=2,
        artifact_hashes={name: item[1] for name, item in parts.items()},
    )
    store = FilesystemDatasetStore(tmp_path)
    manifest_path = store.publish_files(manifest, parts)
    store.activate(manifest, manifest_path)

    rows = DuckDBSnapshotQuery(tmp_path).query_parquet_set(
        manifest,
        tuple(sorted(parts)),
        "SELECT min(close), max(close) FROM {dataset}",
    )

    assert rows == [(10.0, 11.0)]


def test_empty_sparse_event_partition_keeps_an_explicit_schema(tmp_path: Path) -> None:
    payload = DuckDBParquetEncoder().encode((), SUSPENSION_EVENT_COLUMNS)
    path = tmp_path / "empty-suspension.parquet"
    path.write_bytes(payload)

    with duckdb.connect(":memory:") as connection:
        count = connection.execute(
            "SELECT count(*) FROM read_parquet(?)",
            [str(path)],
        ).fetchone()
        columns = connection.execute(
            "DESCRIBE SELECT * FROM read_parquet(?)",
            [str(path)],
        ).fetchall()

    assert count == (0,)
    assert [row[0] for row in columns][-4:] == [
        "instrument_id",
        "trade_date",
        "suspension_timing",
        "suspension_type",
    ]
