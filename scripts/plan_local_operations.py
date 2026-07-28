"""Evaluate the approved local daily operations window."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from astramind_mini.local_ops import evaluate_daily_window


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trading-date", required=True, type=datetime.fromisoformat)
    parser.add_argument("--next-trading-date", required=True, type=datetime.fromisoformat)
    parser.add_argument("--at", required=True, type=datetime.fromisoformat)
    parser.add_argument("--provider-complete", action="store_true")
    parser.add_argument("--pipeline-completed", action="store_true")
    parser.add_argument("--backup-ready", action="store_true")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("var/control/local-operations/decisions"),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    decision = evaluate_daily_window(
        trading_date=args.trading_date.date(),
        next_trading_date=args.next_trading_date.date(),
        evaluated_at=args.at,
        provider_complete=args.provider_complete,
        pipeline_completed=args.pipeline_completed,
        backup_ready=args.backup_ready,
    )
    output = args.output_root / f"{decision.decision_id.rsplit(':', 1)[-1]}.json"
    _write_once(output, decision.model_dump_json(indent=2))
    print(f"operations_decision_id={decision.decision_id}")
    print(f"phase={decision.phase}")
    print(f"status={decision.status}")
    print(f"task_count={len(decision.task_ids)}")
    print(f"blocker_count={len(decision.blocker_codes)}")
    print("paper_preflight_ready=false")
    print("broker_actions_allowed=false")
    return 0 if decision.status in {"ready", "waiting"} else 2


def _write_once(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_text(encoding="utf-8") != payload:
            raise ValueError("本地运行窗口决定身份发生内容冲突")
        return
    temporary = path.with_suffix(".tmp")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


if __name__ == "__main__":
    raise SystemExit(main())
