"""Run the Paper canary read-only preflight without proposals or orders."""

from __future__ import annotations

import argparse
import asyncio

from astramind_mini.config import Settings
from astramind_mini.paper_canary_preflight import PaperCanaryPreflight
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError


async def run() -> int:
    result = await PaperCanaryPreflight(Settings()).run()
    print("state=ready")
    print(f"authorization_id={result.authorization_id}")
    print(f"account_baseline_id={result.account_baseline_id}")
    print(f"instrument_id={result.instrument_id}")
    print(f"submission_window={result.window_state}")
    print(f"quote_market_time={result.quote_market_time.isoformat()}")
    print(f"quote_received_at={result.quote_received_at.isoformat()}")
    print(f"quote_age_seconds={result.quote_age_seconds:.3f}")
    print(f"proposal_count_delta={result.proposal_count_delta}")
    print(f"order_intent_count_delta={result.order_intent_count_delta}")
    print(f"broker_write_attempts={result.broker_write_attempts}")
    print("broker_actions_allowed=false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="只读验证 Paper 金丝雀账户、行情和授权；不生成提案或订单"
    )
    parser.parse_args()
    try:
        return asyncio.run(run())
    except KeyboardInterrupt:
        print("state=interrupted")
        print("broker_write_attempts=0")
        print("broker_actions_allowed=false")
        return 130
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else str(error)
        print(f"blocked={code}")
        print("broker_write_attempts=0")
        print("broker_actions_allowed=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
