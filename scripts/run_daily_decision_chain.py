"""Run or inspect the broker-free WP-0029 daily decision chain."""

from __future__ import annotations

import argparse
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.daily_decision import DailyDecisionOrchestrator
from astramind_mini.local_ops.daily_decision_store import DailyDecisionStore

SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--status", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    artifact_root = Path("var/research/daily-decision")
    store = DailyDecisionStore(settings.local_ops_db_path, artifact_root)
    if args.status:
        status = store.latest_status()
        if status is None:
            print("state=waiting_data")
            print("paper_dispatch_state=disabled")
            print("broker_actions_allowed=false")
            return 0
        _print_status(status.model_dump(mode="json"))
        return 0
    orchestrator = DailyDecisionOrchestrator(
        data_root=settings.data_dir,
        data_control_db=settings.control_db_path,
        promotion_db=Path("var/research/promotions.sqlite3"),
        evidence_root=Path("var/research/sealed"),
        shadow_db=settings.shadow_db_path,
        local_ops_db=settings.local_ops_db_path,
        artifact_root=artifact_root,
        backup_root=(settings.backup_dir / "astramind-mini" if settings.backup_dir else None),
        recovery_root=settings.recovery_drill_dir,
        authorization_root=Path("var/control/paper-canary"),
    )
    with chain_lock(Path("var/control/daily-decision.lock")):
        result = orchestrator.run(started_at=datetime.now(SHANGHAI))
    _print_status(result.status.model_dump(mode="json"))
    if result.artifact_path:
        print(f"artifact_path={result.artifact_path}")
    return 0


def _print_status(value: dict[str, object]) -> None:
    for field in (
        "state",
        "signal_date",
        "feature_snapshot_id",
        "prediction_batch_id",
        "portfolio_target_id",
        "order_plan_id",
        "shadow_preflight_state",
        "paper_preflight_state",
        "recovery_action",
    ):
        if value.get(field) is not None:
            print(f"{field}={value[field]}")
    blockers = value.get("blocker_codes")
    blocker_values = (
        tuple(str(item) for item in blockers) if isinstance(blockers, (list, tuple)) else ()
    )
    print("blocker_codes=" + (",".join(blocker_values) if blocker_values else "none"))
    print("paper_dispatch_state=disabled")
    print("broker_connection_attempts=0")
    print("broker_write_attempts=0")
    print("broker_actions_allowed=false")


@contextmanager
def chain_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("日度研究决策链已有进程在运行") from error
        yield


if __name__ == "__main__":
    raise SystemExit(main())
