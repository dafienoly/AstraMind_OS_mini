"""One interactive, resumable command for the first Paper canary."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.paper_canary_workflow import (
    ActiveCanary,
    PaperCanaryWorkflow,
    expected_approval_text,
    workflow_start_delay,
)
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError

SHANGHAI = ZoneInfo("Asia/Shanghai")
TERMINAL_STATES = {"filled", "cancelled", "rejected"}
CANCEL_TEXT = "撤销本次金丝雀剩余委托"


async def _wait_for_window(workflow: PaperCanaryWorkflow) -> None:
    authorization = workflow.runtime.authorization()
    delay = workflow_start_delay(datetime.now(UTC), authorization)
    while delay > 0:
        print(f"state=waiting_for_submission_window seconds_remaining={int(delay)}")
        await asyncio.sleep(min(30, delay))
        delay = workflow_start_delay(datetime.now(UTC), authorization)


def _print_summary(active_or_staged: object) -> None:
    proposal = getattr(active_or_staged, "proposal", None)
    authorization = getattr(active_or_staged, "authorization", None)
    if proposal is None or authorization is None:
        return
    print("----- 准确 Paper 金丝雀摘要 -----")
    print(f"instrument_id={proposal.instrument_id}")
    print(f"side={proposal.side}")
    print(f"quantity={proposal.quantity}")
    print(f"exact_limit_price={proposal.exact_limit_price:.2f}")
    print(f"proposed_notional_cny={proposal.proposed_notional_cny:.2f}")
    print(f"quote_market_time={proposal.quote_market_time.isoformat()}")
    print(f"account_baseline_id={proposal.account_baseline_id}")
    print(f"standing_mandate_id={authorization.standing_mandate.standing_mandate_id}")
    print(f"portfolio_target_id={authorization.source_portfolio_target_id}")
    print(f"submission_window_end={authorization.submission_window_end.isoformat()}")
    print("cancel_scope=this_canary_only")


async def _monitor(
    workflow: PaperCanaryWorkflow,
    active: ActiveCanary,
) -> int:
    submission_end = workflow.runtime.authorization().submission_window_end
    cancel_prompt_at = submission_end - timedelta(minutes=1)
    while True:
        projection = active.projection
        print(
            f"state={projection.state} filled={projection.cumulative_filled_quantity} "
            f"remaining={projection.remaining_quantity} "
            f"recovery_required={str(projection.recovery_required).lower()}"
        )
        if str(projection.state) in TERMINAL_STATES:
            return 0
        now = datetime.now(UTC)
        if now >= cancel_prompt_at:
            if str(projection.state) in {"acknowledged", "partially_filled"}:
                confirmation = input(f"如需撤销剩余委托，请完整输入“{CANCEL_TEXT}”，否则直接回车：")
                if confirmation.strip() == CANCEL_TEXT:
                    active = await workflow.cancel(active)
                    continue
                print("state=monitoring_stopped automatic_resubmit=false")
                return 3
            if now >= submission_end:
                print("state=monitoring_stopped automatic_resubmit=false")
                return 3
        await asyncio.sleep(5)
        active = await workflow.refresh(active)


async def run() -> int:
    workflow = PaperCanaryWorkflow(Settings())
    try:
        active = workflow.latest_active()
    except KeyError:
        active = None
    if active is not None:
        print(f"state=resuming intent_id={active.intent.intent_id}")
        return await _monitor(workflow, active)
    await _wait_for_window(workflow)
    staged = await workflow.stage()
    _print_summary(staged)
    expected = expected_approval_text(staged.proposal)
    print(f"请输入以下完整确认文本：{expected}")
    approval = workflow.approve(staged, input("确认："))
    print(f"state=approved_locally approval_id={approval.approval_id}")
    active = await workflow.submit(approval)
    print(f"intent_id={active.intent.intent_id}")
    print(f"order_plan_id={active.intent.order_plan.order_plan_id}")
    return await _monitor(workflow, active)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="运行唯一 Paper 金丝雀；准确文本确认前不会产生券商写入"
    )
    parser.parse_args()
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("state=interrupted automatic_resubmit=false recovery=query_only")
        return 130
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else str(error)
        print(f"blocked={code}")
        print("automatic_resubmit=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
