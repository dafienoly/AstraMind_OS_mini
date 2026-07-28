from __future__ import annotations

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from astramind_mini.local_ops.backup import (
    LocalBackupService,
    configuration_fingerprint,
    retained_backup_ids,
)
from astramind_mini.local_ops.contracts import BackupManifest
from astramind_mini.local_ops.recovery import LocalRecoveryDrill
from astramind_mini.local_ops.scheduling import evaluate_daily_window

SHANGHAI = ZoneInfo("Asia/Shanghai")
NOW = datetime(2026, 7, 28, 10, tzinfo=UTC)


def test_daily_windows_fail_closed_and_never_enable_paper() -> None:
    post_close = evaluate_daily_window(
        trading_date=date(2026, 7, 28),
        next_trading_date=date(2026, 7, 29),
        evaluated_at=datetime(2026, 7, 28, 16, 35, tzinfo=SHANGHAI),
        provider_complete=False,
        pipeline_completed=False,
        backup_ready=False,
    )
    stale = evaluate_daily_window(
        trading_date=date(2026, 7, 28),
        next_trading_date=date(2026, 7, 29),
        evaluated_at=datetime(2026, 7, 28, 17, 1, tzinfo=SHANGHAI),
        provider_complete=True,
        pipeline_completed=False,
        backup_ready=False,
    )
    pre_open = evaluate_daily_window(
        trading_date=date(2026, 7, 28),
        next_trading_date=date(2026, 7, 29),
        evaluated_at=datetime(2026, 7, 29, 8, 45, tzinfo=SHANGHAI),
        provider_complete=True,
        pipeline_completed=True,
        backup_ready=False,
    )

    assert post_close.status == "blocked"
    assert post_close.blocker_codes == ("provider_not_complete",)
    assert stale.status == "stale"
    assert stale.blocker_codes == ("daily_pipeline_budget_exceeded",)
    assert pre_open.status == "blocked"
    assert pre_open.blocker_codes == ("backup_or_recovery_not_ready",)
    assert all(
        item.paper_preflight_ready is False and item.broker_actions_allowed is False
        for item in (post_close, stale, pre_open)
    )


def test_external_backup_and_isolated_recovery_are_idempotent(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    backup_root = tmp_path / "backups"
    repository.mkdir()
    control = repository / "var/control/astramind.db"
    shadow = repository / "var/control/shadow.sqlite3"
    _sqlite(control, "CREATE TABLE snapshots (identity TEXT PRIMARY KEY)", ("snapshot:test",))
    _sqlite(
        shadow,
        "CREATE TABLE shadow_events (execution_event_id TEXT PRIMARY KEY)",
        ("event:test",),
    )
    pointers = repository / "var/data/current"
    pointers.mkdir(parents=True)
    (pointers / "data-snapshot.json").write_text(
        json.dumps({"snapshot_id": "snapshot:test"}),
        encoding="utf-8",
    )
    service = LocalBackupService(repository_root=repository, backup_root=backup_root)
    fingerprint = configuration_fingerprint({"environment": "test", "api_host": "127.0.0.1"})
    first = _create_backup(service, control, shadow, pointers, fingerprint)
    second = _create_backup(service, control, shadow, pointers, fingerprint)

    assert first == second
    assert first.status == "complete"
    assert first.paper_backup_ready is True
    assert first.broker_actions_allowed is False
    assert all(not Path(item.relative_path).is_absolute() for item in first.files)
    encoded = first.model_dump_json()
    assert str(repository) not in encoded
    assert str(backup_root) not in encoded

    drill = LocalRecoveryDrill(
        backup_namespace=service.namespace,
        drill_root=repository / "var/recovery-drills",
    )
    report = drill.run(
        backup_id=first.backup_id,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=2),
    )
    repeated = drill.run(
        backup_id=first.backup_id,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=2),
    )
    assert report == repeated
    assert report.status == "healthy"
    assert report.sqlite_integrity_count == 2
    assert report.shadow_event_count == 1
    assert report.paper_recovery_ready is True
    assert report.broker_actions_allowed is False


def test_tampered_backup_blocks_recovery_and_in_repo_root_is_rejected(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    with pytest.raises(ValueError, match="仓库和 var"):
        LocalBackupService(
            repository_root=repository,
            backup_root=repository / "var/backups",
        )

    backup_root = tmp_path / "backups"
    database = repository / "var/control/astramind.db"
    shadow = repository / "var/control/shadow.sqlite3"
    _sqlite(database, "CREATE TABLE state (identity TEXT PRIMARY KEY)", ("state:test",))
    _sqlite(shadow, "CREATE TABLE shadow_events (identity TEXT PRIMARY KEY)", ("event:test",))
    pointers = repository / "var/data/current"
    pointers.mkdir(parents=True)
    (pointers / "data-snapshot.json").write_text("{}", encoding="utf-8")
    service = LocalBackupService(repository_root=repository, backup_root=backup_root)
    manifest = service.create(
        reason="manual",
        logical_date=date(2026, 7, 28),
        created_at=NOW,
        sqlite_sources={"control": database, "shadow": shadow},
        required_sqlite=frozenset({"control", "shadow"}),
        pointer_directory=pointers,
        configuration_fingerprint="sha256:" + "a" * 64,
    )
    backup_dir = next((service.namespace / "daily").glob("*/*"))
    (backup_dir / "sqlite/control.sqlite3").write_bytes(b"tampered")

    report = LocalRecoveryDrill(
        backup_namespace=service.namespace,
        drill_root=repository / "var/recovery-drills",
    ).run(
        backup_id=manifest.backup_id,
        started_at=NOW,
        completed_at=NOW + timedelta(seconds=1),
    )
    assert report.status == "blocked"
    assert "content_mismatch:control" in report.blocker_codes
    assert report.paper_recovery_ready is False


def test_retention_keeps_latest_thirty_and_twelve_month_end_points() -> None:
    manifests = []
    for index in range(40):
        logical_date = date(2026, 7, 28) - timedelta(days=index)
        manifests.append(_manifest(index, logical_date))
    for month in range(1, 14):
        year = 2025 + (month - 1) // 12
        month_number = (month - 1) % 12 + 1
        manifests.append(_manifest(100 + month, date(year, month_number, 28)))

    retained = retained_backup_ids(tuple(manifests))
    ordered = sorted(
        manifests,
        key=lambda item: (item.logical_date, item.created_at, item.backup_id),
        reverse=True,
    )
    assert {item.backup_id for item in ordered[:30]}.issubset(retained)
    month_end: dict[str, BackupManifest] = {}
    for item in ordered:
        month_end.setdefault(item.logical_date.strftime("%Y-%m"), item)
    for month_key in sorted(month_end, reverse=True)[:12]:
        assert month_end[month_key].backup_id in retained


def _sqlite(path: Path, statement: str, row: tuple[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.execute(statement)
        table = statement.split()[2]
        connection.execute(f"INSERT INTO {table} VALUES (?)", row)


def _create_backup(
    service: LocalBackupService,
    control: Path,
    shadow: Path,
    pointers: Path,
    fingerprint: str,
) -> BackupManifest:
    return service.create(
        reason="daily_close",
        logical_date=date(2026, 7, 28),
        created_at=NOW,
        sqlite_sources={"control": control, "shadow": shadow},
        required_sqlite=frozenset({"control", "shadow"}),
        pointer_directory=pointers,
        configuration_fingerprint=fingerprint,
    )


def _manifest(index: int, logical_date: date) -> BackupManifest:
    digest = f"sha256:{index:064x}"
    return BackupManifest(
        backup_id=f"local-backup:{index}",
        reason="daily_close",
        logical_date=logical_date,
        created_at=datetime.combine(logical_date, datetime.min.time(), UTC),
        status="complete",
        files=(),
        configuration_fingerprint=digest,
        paper_backup_ready=True,
        content_hash=digest,
    )
