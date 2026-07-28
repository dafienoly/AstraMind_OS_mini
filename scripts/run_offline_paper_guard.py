"""Run the resumable local-only Paper readiness guard."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.local_ops import OfflineDailyGuard, OfflineGuardInputs, OfflineGuardStore

ROOT = Path(__file__).resolve().parents[1]
SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logical-date", type=date.fromisoformat)
    parser.add_argument("--cycle-artifact", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = Settings()
    now = datetime.now(UTC)
    logical_date = args.logical_date or now.astimezone(SHANGHAI).date()
    cycle_path = args.cycle_artifact or _unique_cycle()
    inputs = _discover_inputs(settings, cycle_path, now)
    run = OfflineDailyGuard(OfflineGuardStore(settings.local_ops_db_path)).run(
        logical_date=logical_date,
        owner_id=f"offline-paper-guard:{logical_date.isoformat()}",
        inputs=inputs,
        started_at=now,
    )
    print(f"run_id={run.run_id}")
    print(f"status={run.state}")
    print(f"completed_task_count={sum(item.state == 'completed' for item in run.task_results)}")
    print(f"blocker_codes={','.join(run.blocker_codes) or 'none'}")
    print("paper_dispatch_state=disabled")
    print("broker_connection_attempts=0")
    print("broker_write_attempts=0")
    print("broker_actions_allowed=false")
    return 0 if run.state == "completed" else 2


def _discover_inputs(settings: Settings, cycle_path: Path, now: datetime) -> OfflineGuardInputs:
    cycle = _json(cycle_path)
    current = _json(settings.data_dir / "current/data-snapshot.json")
    feature = cast(dict[str, Any], cycle.get("feature_snapshot", {}))
    prediction = cast(dict[str, Any], cycle.get("prediction_batch", {}))
    target = cast(dict[str, Any], cycle.get("portfolio_target", {}))
    order_plan_wrapper = cast(dict[str, Any], cycle.get("order_plan", {}))
    order_plan = cast(dict[str, Any], order_plan_wrapper.get("order_plan", {}))
    authorization = _latest_authorization()
    backup_id, recovery_id = _latest_backup_recovery(settings)
    foreign_orders, submission_unknown = _paper_flags(settings.shadow_db_path)
    mandate_end = authorization.get("standing_mandate", {}).get("effective_to")
    mandate_active = bool(mandate_end and datetime.fromisoformat(str(mandate_end)) >= now)
    return OfflineGuardInputs(
        backup_id=backup_id,
        recovery_report_id=recovery_id,
        data_snapshot_id=str(feature.get("data_snapshot_id") or "") or None,
        feature_snapshot_id=str(feature.get("feature_snapshot_id") or "") or None,
        prediction_batch_id=str(prediction.get("prediction_batch_id") or "") or None,
        portfolio_target_id=str(target.get("portfolio_target_id") or "") or None,
        order_plan_id=str(order_plan.get("order_plan_id") or "") or None,
        mandate_preview_id=str(authorization.get("authorization_id") or "") or None,
        data_fresh=feature.get("data_snapshot_id") == current.get("snapshot_id"),
        foreign_open_order_count=foreign_orders,
        mandate_active=mandate_active,
        submission_unknown=submission_unknown,
    )


def _unique_cycle() -> Path:
    matches = tuple(sorted((ROOT / "var/research/continuous-shadow").glob("*/cycle.json")))
    if len(matches) != 1:
        raise RuntimeError("无法唯一发现持续 Shadow 周期，请传入 --cycle-artifact")
    return matches[0]


def _latest_authorization() -> dict[str, Any]:
    matches = tuple(sorted((ROOT / "var/control/paper-canary").glob("*/authorization.json")))
    return _json(matches[-1]) if matches else {}


def _latest_backup_recovery(settings: Settings) -> tuple[str | None, str | None]:
    if settings.backup_dir is None:
        return None, None
    manifests = tuple(
        sorted((settings.backup_dir / "astramind-mini/daily").glob("*/*/manifest.json"))
    )
    healthy = [item for item in manifests if _json(item).get("status") == "complete"]
    if not healthy:
        return None, None
    backup_id = str(_json(healthy[-1]).get("backup_id"))
    reports = tuple(sorted(settings.recovery_drill_dir.glob("*/report.json")))
    matching = [
        _json(path)
        for path in reports
        if _json(path).get("backup_id") == backup_id and _json(path).get("status") == "healthy"
    ]
    recovery_id = str(matching[-1].get("report_id")) if matching else None
    return backup_id, recovery_id


def _paper_flags(database: Path) -> tuple[int, bool]:
    if not database.is_file():
        return 0, False
    with sqlite3.connect(database) as connection:
        baseline = _latest_payload(connection, "paper_account_baselines")
        projection = _latest_payload(connection, "paper_order_projections")
    open_orders = baseline.get("open_order_fingerprints", []) if baseline else []
    unknown = bool(projection and projection.get("state") == "submission_unknown")
    return len(open_orders) if isinstance(open_orders, list) else 0, unknown


def _latest_payload(connection: sqlite3.Connection, table: str) -> dict[str, Any] | None:
    exists = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    if not exists:
        return None
    row = connection.execute(
        f"SELECT payload_json FROM {table} ORDER BY rowid DESC LIMIT 1"
    ).fetchone()
    return cast(dict[str, Any], json.loads(str(row[0]))) if row else None


def _json(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


if __name__ == "__main__":
    raise SystemExit(main())
