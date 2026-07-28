"""Stage an exact Paper canary limit from a fresh read-only baseline and L1 quote."""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.miniqmt_canary_quote import (
    MiniQMTCanaryQuoteReader,
)
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.contracts.paper_canary import (
    PaperCanaryAuthorization,
)
from astramind_mini.trading_execution.domain import build_paper_limit_proposal

ROOT = Path(__file__).resolve().parents[1]


def _latest(database: Path, table: str, *, order_by: str = "rowid") -> dict[str, Any]:
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            f"SELECT payload_json FROM {table} ORDER BY {order_by} DESC LIMIT 1"
        ).fetchone()
    if row is None:
        raise ValueError(f"{table}_missing")
    return cast(dict[str, Any], json.loads(str(row[0])))


async def stage(settings: Settings) -> int:
    authorization = PaperCanaryAuthorization.model_validate(
        _latest(settings.shadow_db_path, "paper_canary_authorizations")
    )
    baseline = _latest(settings.shadow_db_path, "paper_account_baselines", order_by="created_at")
    baseline_at = datetime.fromisoformat(str(baseline["created_at"]))
    now = datetime.now(UTC)
    if now - baseline_at > timedelta(minutes=2):
        raise ValueError("paper_account_baseline_stale")
    if baseline.get("open_order_fingerprints"):
        raise ValueError("unexpected_open_orders")
    quote = await MiniQMTCanaryQuoteReader(
        runner=ROOT / "scripts/windows/miniqmt_canary_quote.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        quote_port=settings.miniqmt_quote_port,
        timeout_seconds=settings.miniqmt_probe_timeout_seconds,
    ).read(authorization.instrument_id)
    if not quote.tradable:
        raise ValueError("canary_instrument_not_tradable")
    proposal = build_paper_limit_proposal(
        authorization=authorization,
        account_baseline_id=str(baseline["baseline_id"]),
        best_ask=quote.best_ask,
        quote_market_time=quote.market_time,
        quote_received_at=quote.received_at,
    )
    PaperContinuousStore(settings.shadow_db_path).publish_proposal(proposal)
    directory = settings.shadow_db_path.parent / "paper-canary" / proposal.content_hash[7:]
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "limit-proposal.json"
    encoded = proposal.model_dump_json(indent=2)
    if path.exists() and path.read_text(encoding="utf-8") != encoded:
        raise ValueError("paper_limit_proposal_conflict")
    path.write_text(encoded, encoding="utf-8")
    print(f"proposal_id={proposal.proposal_id}")
    print(f"instrument_id={proposal.instrument_id}")
    print(f"quantity={proposal.quantity}")
    print(f"exact_limit_price={proposal.exact_limit_price:.2f}")
    print(f"proposed_notional_cny={proposal.proposed_notional_cny:.2f}")
    print(f"quote_market_time={proposal.quote_market_time.isoformat()}")
    print(f"account_baseline_id={proposal.account_baseline_id}")
    print(f"authorization_id={authorization.authorization_id}")
    print(f"standing_mandate_id={authorization.standing_mandate.standing_mandate_id}")
    print(f"portfolio_target_id={authorization.source_portfolio_target_id}")
    print(f"submission_window_end={authorization.submission_window_end.isoformat()}")
    print("cancel_scope=this_canary_only")
    print("state=awaiting_user_approval")
    print("broker_actions_allowed=false")
    return 0


def main() -> int:
    try:
        return asyncio.run(stage(Settings()))
    except (MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked={code}")
        print("broker_actions_allowed=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
