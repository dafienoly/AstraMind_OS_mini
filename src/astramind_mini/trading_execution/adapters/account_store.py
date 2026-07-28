"""Content-addressed account evidence with an append-only SQLite/WAL index."""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from ..contracts.account import AccountSnapshot, ReconciliationReport
from ..domain.reconciliation import canonical_hash


class FilesystemAccountReconciliationStore:
    def __init__(
        self,
        *,
        root: Path,
        database: Path,
        migrations: Path | None = None,
    ) -> None:
        self._root = root
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
                str(row[0]) for row in connection.execute("SELECT version FROM schema_migrations")
            }
            for path in sorted(self._migrations.glob("*.sql")):
                if path.stem in applied:
                    continue
                connection.executescript(path.read_text(encoding="utf-8"))
                connection.execute(
                    "INSERT INTO schema_migrations VALUES (?, ?)",
                    (path.stem, datetime.now(UTC).isoformat()),
                )

    def publish_account_snapshot(self, snapshot: AccountSnapshot) -> Path:
        self._verify_snapshot(snapshot)
        path = self._artifact("account-snapshots", snapshot.content_hash, snapshot)
        self._record(
            table="account_snapshot_publications",
            identity=snapshot.account_snapshot_id,
            content_hash=snapshot.content_hash,
            artifact_path=path,
            state=snapshot.account_mode,
            occurred_at=snapshot.as_of,
        )
        return path

    def publish_reconciliation(self, report: ReconciliationReport) -> Path:
        self._verify_report(report)
        path = self._artifact("reconciliations", report.content_hash, report)
        self._record(
            table="reconciliation_publications",
            identity=report.reconciliation_report_id,
            content_hash=report.content_hash,
            artifact_path=path,
            state=report.status,
            occurred_at=report.created_at,
        )
        return path

    def journal_mode(self) -> str:
        with self._connect() as connection:
            row = connection.execute("PRAGMA journal_mode").fetchone()
        return str(row[0])

    def publication_counts(self) -> tuple[int, int]:
        with self._connect() as connection:
            snapshots = connection.execute(
                "SELECT count(*) FROM account_snapshot_publications"
            ).fetchone()
            reports = connection.execute(
                "SELECT count(*) FROM reconciliation_publications"
            ).fetchone()
        return int(snapshots[0]), int(reports[0])

    def read_account_snapshot(self, identity: str) -> AccountSnapshot:
        return AccountSnapshot.model_validate_json(
            self._published_payload("account_snapshot_publications", identity)
        )

    def read_reconciliation(self, identity: str) -> ReconciliationReport:
        return ReconciliationReport.model_validate_json(
            self._published_payload("reconciliation_publications", identity)
        )

    def _artifact(self, kind: str, content_hash: str, value: object) -> Path:
        digest = content_hash.removeprefix("sha256:")
        path = self._root / kind / digest / "artifact.json"
        payload = _json_bytes(value)
        if path.exists() and path.read_bytes() != payload:
            raise ValueError("账户证据身份发生内容冲突")
        if not path.exists():
            _atomic_write(path, payload)
        return path

    def _record(
        self,
        *,
        table: str,
        identity: str,
        content_hash: str,
        artifact_path: Path,
        state: str,
        occurred_at: datetime,
    ) -> None:
        self.migrate()
        relative = str(artifact_path.relative_to(self._root))
        with self._connect() as connection:
            existing = connection.execute(
                f"SELECT content_hash, artifact_path, state FROM {table} WHERE identity = ?",
                (identity,),
            ).fetchone()
            expected = (content_hash, relative, state)
            if existing is not None:
                if tuple(existing) != expected:
                    raise ValueError("账户证据台账身份冲突")
                return
            connection.execute(
                f"INSERT INTO {table} VALUES (?, ?, ?, ?, ?)",
                (identity, content_hash, relative, state, occurred_at.isoformat()),
            )

    def _verify_snapshot(self, snapshot: AccountSnapshot) -> None:
        identity = {
            "provider": snapshot.provider,
            "account_mode": snapshot.account_mode,
            "account_fingerprint": snapshot.account_fingerprint,
            "as_of": snapshot.as_of,
            "trading_date": snapshot.trading_date,
            "cash": snapshot.cash.model_dump(mode="json"),
            "positions": [item.model_dump(mode="json") for item in snapshot.positions],
            "orders": [item.model_dump(mode="json") for item in snapshot.orders],
            "trades": [item.model_dump(mode="json") for item in snapshot.trades],
            "client_version": snapshot.client_version,
            "gateway_version": snapshot.gateway_version,
            "known_gaps": list(snapshot.known_gaps),
        }
        digest = canonical_hash(identity)
        expected = "account-snapshot:" + digest.removeprefix("sha256:")
        if digest != snapshot.content_hash or snapshot.account_snapshot_id != expected:
            raise ValueError("账户快照内容身份校验失败")

    def _verify_report(self, report: ReconciliationReport) -> None:
        identity = {
            "local_projection_id": report.local_projection_id,
            "account_snapshot_id": report.account_snapshot_id,
            "account_mode": report.account_mode,
            "cash_difference": (
                report.cash_difference.model_dump(mode="json") if report.cash_difference else None
            ),
            "position_differences": [
                item.model_dump(mode="json") for item in report.position_differences
            ],
            "unexpected_open_order_fingerprints": report.unexpected_open_order_fingerprints,
            "missing_open_order_fingerprints": report.missing_open_order_fingerprints,
            "blocker_codes": report.blocker_codes,
            "created_at": report.created_at,
        }
        digest = canonical_hash(identity)
        expected = "reconciliation-report:" + digest.removeprefix("sha256:")
        if digest != report.content_hash or report.reconciliation_report_id != expected:
            raise ValueError("对账报告内容身份校验失败")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _published_payload(self, table: str, identity: str) -> bytes:
        self.migrate()
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT artifact_path FROM {table} WHERE identity = ?", (identity,)
            ).fetchone()
        if row is None:
            raise KeyError(identity)
        path = self._root / str(row[0])
        if not path.is_file():
            raise ValueError("账户证据文件缺失")
        return path.read_bytes()


def _json_bytes(value: object) -> bytes:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = ["FilesystemAccountReconciliationStore"]
