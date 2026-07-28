"""Create the post-close broker/local convergence report for the Paper canary."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.paper_runtime_composition import (
    account_store,
    fresh_startup,
    paper_gateway,
)
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.adapters.paper_store import PaperExecutionStore
from astramind_mini.trading_execution.application.paper_continuous import (
    ContinuousPaperExecutionService,
)
from astramind_mini.trading_execution.domain.paper_runtime import (
    build_convergence_report,
    validate_canary_control_scope,
)


async def converge(args: argparse.Namespace, settings: Settings) -> int:
    now = datetime.now(UTC)
    shanghai_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if shanghai_now.time() < time(15, 0):
        raise ValueError("post_close_convergence_only")
    runtime = PaperRuntimeStore(settings.shadow_db_path)
    approval = runtime.approval(args.approval_id)
    proposal = runtime.proposal(approval.proposal_id)
    repository = PaperExecutionStore(settings.shadow_db_path)
    intent = (
        repository.read_intent(args.intent_id) if args.intent_id else repository.latest_intent()
    )
    authorization = runtime.authorization(approval.authorization_id)
    validate_canary_control_scope(
        intent_instrument_id=intent.instrument_id,
        intent_quantity=intent.quantity,
        intent_limit_price=intent.limit_price,
        intent_portfolio_target_id=intent.order_plan.portfolio_target_id,
        intent_standing_mandate_id=intent.order_plan.standing_mandate_id,
        approval=approval,
        proposal=proposal,
        authorization=authorization,
    )
    service = ContinuousPaperExecutionService(
        repository=repository,
        commands=PaperContinuousStore(settings.shadow_db_path),
        gateway=paper_gateway(settings),
    )
    projection = await service.refresh(intent)
    publication = await fresh_startup(settings)
    starting_baseline = runtime.baseline(proposal.account_baseline_id)
    accounts = account_store(settings)
    starting = accounts.read_account_snapshot(starting_baseline.account_snapshot_id)
    report = build_convergence_report(
        intent_id=intent.intent_id,
        instrument_id=intent.instrument_id,
        starting=starting,
        ending=publication.account_snapshot,
        projection=projection,
        created_at=datetime.now(UTC),
    )
    runtime.publish_convergence(report)
    print(f"report_id={report.report_id}")
    print(f"status={report.status}")
    print(f"managed_quantity={report.managed_quantity}")
    print(f"broker_trade_quantity={report.broker_trade_quantity}")
    print(f"open_canary_order_count={report.open_canary_order_count}")
    print(f"blocker_codes={','.join(report.blocker_codes)}")
    print(f"future_orders_frozen={str(report.status != 'converged').lower()}")
    return 0 if report.status == "converged" else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--intent-id")
    try:
        return asyncio.run(converge(parser.parse_args(), Settings()))
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked={code}")
        print("future_orders_frozen=true")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
