"""SQLite/WAL control ledger for immutable Data artifacts."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from astramind_mini.contracts import DataSnapshot

from ..application.identity import bytes_hash
from ..contracts import DatasetManifest, ProbeReport


class DataControlLedger:
    def __init__(self, database: Path, migrations: Path | None = None) -> None:
        self._database = database
        self._migrations = migrations or Path(__file__).with_name("sqlite") / "migrations"

    def migrate(self) -> None:
        self._database.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {
                row[0] for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for path in sorted(self._migrations.glob("*.sql")):
                if path.stem in applied:
                    continue
                connection.executescript(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (path.stem, datetime.now(UTC).isoformat()),
                )

    def record_probe(self, report: ProbeReport, report_path: Path) -> None:
        payload = report_path.read_bytes()
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO provider_probe_runs VALUES (?, ?, ?, ?, ?)",
                (
                    report.probe_id,
                    report.provider,
                    report.probed_at.isoformat(),
                    str(report_path),
                    bytes_hash(payload),
                ),
            )

    def record_dataset(self, manifest: DatasetManifest, manifest_path: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO dataset_versions VALUES (?, ?, ?, ?, ?)",
                (
                    manifest.dataset_version,
                    manifest.dataset_name,
                    manifest.retrieved_at.isoformat(),
                    str(manifest_path),
                    manifest.content_hash,
                ),
            )

    def record_snapshot(self, snapshot: DataSnapshot, manifest_path: Path) -> None:
        with self._connect() as connection:
            connection.execute(
                "INSERT OR IGNORE INTO data_snapshots VALUES (?, ?, ?, ?)",
                (
                    snapshot.snapshot_id,
                    snapshot.as_of.isoformat(),
                    snapshot.created_at.isoformat(),
                    str(manifest_path),
                ),
            )

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection


__all__ = ["DataControlLedger"]
