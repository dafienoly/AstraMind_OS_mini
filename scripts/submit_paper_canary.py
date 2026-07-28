"""Explicit one-shot submission for the exactly approved Paper canary."""

from __future__ import annotations

import argparse
import asyncio

from astramind_mini.config import Settings
from astramind_mini.paper_canary_workflow import PaperCanaryWorkflow
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError

CONFIRMATION = "SUBMIT_ONE_APPROVED_PAPER_CANARY"


async def submit(args: argparse.Namespace, settings: Settings) -> int:
    if args.confirm != CONFIRMATION:
        raise ValueError("explicit_submit_confirmation_required")
    workflow = PaperCanaryWorkflow(settings)
    approval = workflow.runtime.approval(args.approval_id)
    active = await workflow.submit(approval)
    projection = active.projection
    print(f"intent_id={active.intent.intent_id}")
    print(f"order_plan_id={active.intent.order_plan.order_plan_id}")
    print(f"state={projection.state}")
    print(f"recovery_required={str(projection.recovery_required).lower()}")
    print("automatic_resubmit=false")
    return 0 if projection.state != "submission_unknown" else 3


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--confirm", required=True)
    try:
        return asyncio.run(submit(parser.parse_args(), Settings()))
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked={code}")
        print("automatic_resubmit=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
