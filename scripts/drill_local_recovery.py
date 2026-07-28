"""Run a non-destructive recovery drill from one exact backup identity."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from astramind_mini.config import Settings
from astramind_mini.local_ops import LocalRecoveryDrill


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--backup-id", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    if settings.backup_dir is None:
        print("status=blocked")
        print("blocker_code=backup_directory_not_configured")
        print("recovery=配置仓库外的 ASTRAMIND_BACKUP_DIR 并先建立备份")
        print("paper_recovery_ready=false")
        print("broker_actions_allowed=false")
        return 2
    report = LocalRecoveryDrill(
        backup_namespace=settings.backup_dir / "astramind-mini",
        drill_root=settings.recovery_drill_dir,
    ).run(
        backup_id=args.backup_id,
        started_at=datetime.now(UTC),
    )
    print(f"recovery_report_id={report.report_id}")
    print(f"backup_id={report.backup_id}")
    print(f"status={report.status}")
    print(f"verified_file_count={report.verified_file_count}")
    print(f"sqlite_integrity_count={report.sqlite_integrity_count}")
    print(f"shadow_event_count={report.shadow_event_count}")
    print(f"paper_recovery_ready={str(report.paper_recovery_ready).lower()}")
    print("broker_actions_allowed=false")
    return 0 if report.status == "healthy" else 2


if __name__ == "__main__":
    raise SystemExit(main())
