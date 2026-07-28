"""Publish the approved Paper canary mandate without contacting the broker."""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters.paper_canary_store import (
    PaperCanaryAuthorizationStore,
)
from astramind_mini.trading_execution.domain.paper_canary import (
    build_paper_canary_authorization,
)

ROOT = Path(__file__).resolve().parents[1]


def _aware(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("时间必须包含 Asia/Shanghai 时区偏移")
    return parsed


def _latest_baseline(database: Path) -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT payload_json FROM paper_account_baselines "
            "ORDER BY created_at DESC, identity DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError("缺少 WP-0017 Paper 账户基线")
    value = cast(dict[str, Any], json.loads(str(row[0])))
    if value["open_order_fingerprints"]:
        raise ValueError("模拟盘存在未完成委托，不能准备金丝雀")
    return value


def _source_line(path: Path, instrument_id: str) -> tuple[str, str]:
    artifact = json.loads(path.read_text(encoding="utf-8"))
    target_id = str(artifact["portfolio_target"]["portfolio_target_id"])
    shadow_plan = artifact["order_plan"]
    lines = [
        line
        for line in shadow_plan["lines"]
        if line["instrument_id"] == instrument_id
        and line["side"] == "buy"
        and not line["blocker_codes"]
    ]
    if len(lines) != 1:
        raise ValueError("准确 PortfolioTarget 中不存在唯一且无阻断的买入目标")
    return target_id, str(shadow_plan["order_plan"]["order_plan_id"])


def run(args: argparse.Namespace) -> int:
    settings = Settings()
    baseline = _latest_baseline(settings.shadow_db_path)
    target_id, shadow_plan_id = _source_line(args.cycle_artifact, args.instrument)
    authorization = build_paper_canary_authorization(
        source_portfolio_target_id=target_id,
        source_shadow_order_plan_id=shadow_plan_id,
        account_baseline_id=str(baseline["baseline_id"]),
        instrument_id=args.instrument,
        quantity=args.quantity,
        max_notional_cny=args.max_notional,
        mandate_start=_aware(args.mandate_start),
        mandate_end=_aware(args.mandate_end),
        submission_start=_aware(args.submission_start),
        submission_end=_aware(args.submission_end),
        approved_at=_aware(args.approved_at),
    )
    PaperCanaryAuthorizationStore(settings.shadow_db_path).publish(authorization)
    directory = settings.shadow_db_path.parent / "paper-canary" / authorization.content_hash[7:]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "authorization.json"
    encoded = authorization.model_dump_json(indent=2)
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("Paper 金丝雀授权文件发生内容冲突")
    path.write_text(encoded, encoding="utf-8")
    print(f"authorization_id={authorization.authorization_id}")
    print(f"standing_mandate_id={authorization.standing_mandate.standing_mandate_id}")
    print(f"portfolio_target_id={authorization.source_portfolio_target_id}")
    print(f"account_baseline_id={authorization.account_baseline_id}")
    print(f"state={authorization.state}")
    print("broker_actions_allowed=false")
    print(f"evidence={path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cycle-artifact", type=Path, required=True)
    parser.add_argument("--instrument", default="605208.SH")
    parser.add_argument("--quantity", type=int, default=100)
    parser.add_argument("--max-notional", type=int, default=50_000)
    parser.add_argument("--mandate-start", required=True)
    parser.add_argument("--mandate-end", required=True)
    parser.add_argument("--submission-start", required=True)
    parser.add_argument("--submission-end", required=True)
    parser.add_argument("--approved-at", required=True)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
