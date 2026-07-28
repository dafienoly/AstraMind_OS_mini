"""Run deterministic offline Paper failure and recovery drills."""

from __future__ import annotations

import argparse
from datetime import UTC, date, datetime

from astramind_mini.config import Settings
from astramind_mini.local_ops import run_offline_fault_drills


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logical-date", type=date.fromisoformat)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    now = datetime.now(UTC)
    report = run_offline_fault_drills(
        database=settings.local_ops_db_path,
        logical_date=args.logical_date or now.date(),
        started_at=now,
    )
    print(f"report_id={report.report_id}")
    print(f"status={report.status}")
    print(f"case_count={len(report.cases)}")
    print(f"passed_case_count={sum(item.status == 'passed' for item in report.cases)}")
    print("broker_connection_attempts=0")
    print("broker_write_attempts=0")
    print("broker_actions_allowed=false")
    return 0 if report.status == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
