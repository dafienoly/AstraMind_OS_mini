"""Evaluate WP-0031 scheduling and invoke only the WP-0030 Make targets."""

from __future__ import annotations

import argparse
import fcntl
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.local_ops.daily_run_store import DailyRunStore
from astramind_mini.local_ops.daily_scheduler import evaluate_daily_schedule
from astramind_mini.local_ops.daily_scheduler_contracts import (
    DailyRunRequest,
    DailyScheduleDecision,
)
from astramind_mini.local_ops.daily_scheduler_store import DailySchedulerStore
from astramind_mini.local_ops.trading_calendar import current_open_dates

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    parser.add_argument("--at", type=datetime.fromisoformat)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def run(args: argparse.Namespace) -> int:
    settings = Settings()
    evaluated_at = args.at or datetime.now(SHANGHAI)
    if evaluated_at.tzinfo is None:
        raise ValueError("--at 必须带时区")
    run_store = DailyRunStore(
        settings.local_ops_db_path,
        Path("var/operations/daily-runs"),
    )
    scheduler_store = DailySchedulerStore(settings.local_ops_db_path)
    pending = (
        scheduler_store.pending_request()
        if args.dry_run
        else scheduler_store.claim_pending(evaluated_at)
    )
    decision = evaluate_daily_schedule(
        open_dates=current_open_dates(settings.data_dir),
        evaluated_at=evaluated_at,
        latest_run=run_store.latest_status(),
    )
    scheduler_store.publish_decision(decision)
    _print_decision(decision.model_dump(mode="json"))
    command = _request_command(pending, args.provider_env_file)
    if command is None:
        command = _decision_command(decision, args.provider_env_file)
    if command is None or args.dry_run:
        print("broker_actions_allowed=false")
        return 0
    completed = subprocess.run(command, check=False)
    if pending and completed.returncode == 0:
        scheduler_store.complete_request(pending, datetime.now(SHANGHAI))
    print(f"command_exit_code={completed.returncode}")
    print("broker_connection_attempts=0")
    print("broker_write_attempts=0")
    print("broker_actions_allowed=false")
    return completed.returncode


def _request_command(
    request: DailyRunRequest | None,
    provider_env_file: Path,
) -> list[str] | None:
    if request is None:
        return None
    if request.action in ("recover", "retry_provider") and request.run_id:
        return [
            "make",
            "daily-run-recover",
            f"PROVIDER_ENV_FILE={provider_env_file}",
            f"RUN_ID={request.run_id}",
        ]
    if request.action == "run" and request.target_date:
        return [
            "make",
            "daily-run",
            f"PROVIDER_ENV_FILE={provider_env_file}",
            f"TARGET_DATE={request.target_date.isoformat()}",
        ]
    return None


def _decision_command(
    decision: DailyScheduleDecision,
    provider_env_file: Path,
) -> list[str] | None:
    if decision.action == "run" and decision.target_date:
        return [
            "make",
            "daily-run",
            f"PROVIDER_ENV_FILE={provider_env_file}",
            f"TARGET_DATE={decision.target_date.isoformat()}",
        ]
    if decision.action == "recover" and decision.run_id:
        return [
            "make",
            "daily-run-recover",
            f"PROVIDER_ENV_FILE={provider_env_file}",
            f"RUN_ID={decision.run_id}",
        ]
    return None


def _print_decision(value: dict[str, object]) -> None:
    for field in (
        "decision_id",
        "evaluated_at",
        "target_date",
        "trigger",
        "action",
        "run_id",
        "reason_code",
        "next_trigger_at",
    ):
        if value.get(field) is not None:
            print(f"{field}={value[field]}")
    blockers = value.get("blocker_codes")
    items = tuple(str(item) for item in blockers) if isinstance(blockers, (list, tuple)) else ()
    print("blocker_codes=" + (",".join(items) if items else "none"))


@contextmanager
def scheduler_lock(path: Path) -> Iterator[bool]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True


def main() -> int:
    args = parse_args()
    with scheduler_lock(Path("var/control/daily-scheduler.lock")) as acquired:
        if not acquired:
            print("state=lease_held")
            print("broker_actions_allowed=false")
            return 0
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
