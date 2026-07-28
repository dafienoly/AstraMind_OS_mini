"""Create one consistent external local control-plane backup."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.local_ops.backup import (
    BackupReason,
    LocalBackupService,
    configuration_fingerprint,
)

ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reason",
        choices=("daily_close", "pre_migration", "pre_first_broker_write", "manual"),
        default="manual",
    )
    parser.add_argument("--logical-date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    if settings.backup_dir is None:
        print("status=blocked")
        print("blocker_code=backup_directory_not_configured")
        print("recovery=配置仓库外的 ASTRAMIND_BACKUP_DIR 后重试")
        print("paper_backup_ready=false")
        print("broker_actions_allowed=false")
        return 2
    now = datetime.now(UTC)
    logical_date = args.logical_date or now.astimezone(ZoneInfo("Asia/Shanghai")).date()
    service = LocalBackupService(repository_root=ROOT, backup_root=settings.backup_dir)
    manifest = service.create(
        reason=cast(BackupReason, args.reason),
        logical_date=logical_date,
        created_at=now,
        sqlite_sources={
            "control": settings.control_db_path,
            "local_ops": settings.local_ops_db_path,
            "shadow": settings.shadow_db_path,
            "promotions": Path("var/research/promotions.sqlite3"),
        },
        required_sqlite=frozenset({"control", "local_ops", "shadow"}),
        pointer_directory=settings.data_dir / "current",
        configuration_fingerprint=configuration_fingerprint(
            {
                "environment": settings.environment,
                "api_host": settings.api_host,
                "api_port": settings.api_port,
                "web_port": settings.web_port,
            }
        ),
    )
    removed = service.prune() if manifest.status == "complete" else ()
    print(f"backup_id={manifest.backup_id}")
    print(f"status={manifest.status}")
    print(f"file_count={len(manifest.files)}")
    print(f"missing_source_count={len(manifest.missing_sources)}")
    print(f"retention_removed_count={len(removed)}")
    print(f"paper_backup_ready={str(manifest.paper_backup_ready).lower()}")
    print("broker_actions_allowed=false")
    return 0 if manifest.status == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
