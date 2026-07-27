import sqlite3
from pathlib import Path

import duckdb


def test_duckdb_in_memory_probe() -> None:
    with duckdb.connect(":memory:") as connection:
        assert connection.execute("select 42").fetchone() == (42,)


def test_sqlite_wal_probe(tmp_path: Path) -> None:
    database = tmp_path / "control.db"
    with sqlite3.connect(database) as connection:
        mode = connection.execute("pragma journal_mode=wal").fetchone()
    assert mode == ("wal",)
