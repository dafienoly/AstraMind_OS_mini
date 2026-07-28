"""Record the user's exact numeric approval without contacting MiniQMT."""

from __future__ import annotations

import argparse
from datetime import datetime

from astramind_mini.config import Settings
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.domain.paper_runtime import build_submission_approval

CONFIRMATION = "APPROVE_EXACT_PAPER_CANARY"


def _aware(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("approval_time_must_include_timezone")
    return result


def run(args: argparse.Namespace) -> int:
    if args.confirm != CONFIRMATION:
        raise ValueError("exact_approval_confirmation_required")
    settings = Settings()
    runtime = PaperRuntimeStore(settings.shadow_db_path)
    proposal = runtime.proposal(args.proposal_id)
    authorization = runtime.authorization(proposal.authorization_id)
    approval = build_submission_approval(
        proposal=proposal,
        authorization=authorization,
        confirmed_limit_price=args.confirm_limit_price,
        approved_at=_aware(args.approved_at),
        effective_to=_aware(args.effective_to),
    )
    PaperContinuousStore(settings.shadow_db_path).publish_approval(approval)
    print(f"approval_id={approval.approval_id}")
    print(f"proposal_id={approval.proposal_id}")
    print(f"instrument_id={proposal.instrument_id}")
    print(f"side={proposal.side}")
    print(f"quantity={proposal.quantity}")
    print(f"exact_limit_price={approval.exact_limit_price:.2f}")
    print(f"maximum_notional_cny={proposal.maximum_notional_cny}")
    print(f"effective_to={approval.effective_to.isoformat()}")
    print("state=approved_locally")
    print("broker_actions_allowed=false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--confirm-limit-price", type=float, required=True)
    parser.add_argument("--approved-at", required=True)
    parser.add_argument("--effective-to", required=True)
    parser.add_argument("--confirm", required=True)
    try:
        return run(parser.parse_args())
    except (KeyError, OSError, ValueError) as error:
        print(f"blocked={type(error).__name__}")
        print("broker_actions_allowed=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
