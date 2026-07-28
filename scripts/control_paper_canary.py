"""Read-only status/recovery and narrowly scoped cancel for the Paper canary."""

from __future__ import annotations

import argparse
import asyncio

from astramind_mini.config import Settings
from astramind_mini.paper_runtime_composition import paper_gateway
from astramind_mini.trading_execution.adapters.miniqmt_account import MiniQMTAccountError
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.adapters.paper_store import PaperExecutionStore
from astramind_mini.trading_execution.application.paper_continuous import (
    ContinuousPaperExecutionService,
)
from astramind_mini.trading_execution.contracts.paper import PaperOrderIntent
from astramind_mini.trading_execution.contracts.paper_continuous import (
    PaperSubmissionApproval,
)
from astramind_mini.trading_execution.domain.paper_runtime import (
    validate_canary_control_scope,
)

CANCEL_CONFIRMATION = "CANCEL_THIS_PAPER_CANARY_ONLY"


def _validate_scope(
    intent: PaperOrderIntent,
    approval: PaperSubmissionApproval,
    runtime: PaperRuntimeStore,
) -> None:
    proposal = runtime.proposal(approval.proposal_id)
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


async def control(args: argparse.Namespace, settings: Settings) -> int:
    repository = PaperExecutionStore(settings.shadow_db_path)
    intent = (
        repository.read_intent(args.intent_id) if args.intent_id else repository.latest_intent()
    )
    runtime = PaperRuntimeStore(settings.shadow_db_path)
    approval = runtime.approval(args.approval_id)
    _validate_scope(intent, approval, runtime)
    service = ContinuousPaperExecutionService(
        repository=repository,
        commands=PaperContinuousStore(settings.shadow_db_path),
        gateway=paper_gateway(settings),
    )
    if args.action == "status":
        projection = await service.refresh(intent)
    elif args.action == "recover":
        projection = await service.recover(intent)
    else:
        if args.confirm != CANCEL_CONFIRMATION:
            raise ValueError("explicit_cancel_confirmation_required")
        projection = await service.cancel(intent=intent, approval=approval)
    print(f"intent_id={intent.intent_id}")
    print(f"state={projection.state}")
    print(f"filled_quantity={projection.cumulative_filled_quantity}")
    print(f"remaining_quantity={projection.remaining_quantity}")
    print(f"recovery_required={str(projection.recovery_required).lower()}")
    print("automatic_resubmit=false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", choices=("status", "recover", "cancel"), required=True)
    parser.add_argument("--approval-id", required=True)
    parser.add_argument("--intent-id")
    parser.add_argument("--confirm")
    try:
        return asyncio.run(control(parser.parse_args(), Settings()))
    except (KeyError, MiniQMTAccountError, OSError, ValueError) as error:
        code = error.code if isinstance(error, MiniQMTAccountError) else type(error).__name__
        print(f"blocked={code}")
        print("automatic_resubmit=false")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
