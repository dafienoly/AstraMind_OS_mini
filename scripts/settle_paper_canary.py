"""Automatically discover and settle the unique first Paper canary after close."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.paper_canary_workflow import PaperCanaryWorkflow
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError


async def settle() -> int:
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    if now.time() < time(15, 0):
        raise ValueError("post_close_convergence_only")
    workflow = PaperCanaryWorkflow(Settings())
    active = workflow.latest_active()
    report = await workflow.settle(active)
    print(f"report_id={report.report_id}")
    print(f"intent_id={report.intent_id}")
    print(f"status={report.status}")
    print(f"managed_quantity={report.managed_quantity}")
    print(f"broker_trade_quantity={report.broker_trade_quantity}")
    print(f"open_canary_order_count={report.open_canary_order_count}")
    print(f"blocker_codes={','.join(report.blocker_codes)}")
    print(f"future_orders_frozen={str(report.status != 'converged').lower()}")
    return 0 if report.status == "converged" else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="盘后自动发现并收敛唯一 Paper 金丝雀")
    parser.parse_args()
    try:
        return asyncio.run(settle())
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else str(error)
        print(f"blocked={code}")
        print("future_orders_frozen=true")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
