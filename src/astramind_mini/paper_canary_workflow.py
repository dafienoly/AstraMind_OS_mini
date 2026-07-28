"""Explicit composition for the resumable first Paper canary workflow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from astramind_mini.config import Settings
from astramind_mini.paper_runtime_composition import (
    account_store,
    fresh_startup,
    paper_gateway,
    quote_reader,
)
from astramind_mini.trading_execution.adapters.paper_continuous_store import (
    PaperContinuousStore,
)
from astramind_mini.trading_execution.adapters.paper_runtime_store import PaperRuntimeStore
from astramind_mini.trading_execution.adapters.paper_store import PaperExecutionStore
from astramind_mini.trading_execution.application.paper_continuous import (
    ContinuousPaperExecutionService,
)
from astramind_mini.trading_execution.contracts.paper import (
    PaperOrderIntent,
    PaperOrderProjection,
)
from astramind_mini.trading_execution.contracts.paper_canary import PaperCanaryAuthorization
from astramind_mini.trading_execution.contracts.paper_continuous import (
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from astramind_mini.trading_execution.contracts.paper_runtime import PaperConvergenceReport
from astramind_mini.trading_execution.domain.paper import (
    build_paper_intent,
    initial_paper_projection,
)
from astramind_mini.trading_execution.domain.paper_continuous import (
    build_paper_limit_proposal,
)
from astramind_mini.trading_execution.domain.paper_runtime import (
    account_drawdown,
    build_convergence_report,
    build_paper_canary_order_plan,
    build_real_paper_preflight,
    build_submission_approval,
    validate_canary_control_scope,
)


@dataclass(frozen=True, slots=True)
class StagedCanary:
    authorization: PaperCanaryAuthorization
    proposal: PaperLimitProposal


@dataclass(frozen=True, slots=True)
class ActiveCanary:
    approval: PaperSubmissionApproval
    intent: PaperOrderIntent
    projection: PaperOrderProjection


def expected_approval_text(proposal: PaperLimitProposal) -> str:
    return (
        f"批准 {proposal.instrument_id} 买入{proposal.quantity}股 "
        f"限价{proposal.exact_limit_price:.2f}，仅提交一次"
    )


def workflow_start_delay(now: datetime, authorization: PaperCanaryAuthorization) -> float:
    start = authorization.submission_window_start
    end = authorization.submission_window_end
    if now > end:
        raise ValueError("paper_submission_window_closed")
    if now >= start:
        return 0
    delay = (start - now).total_seconds()
    if delay > 15 * 60:
        raise ValueError("paper_workflow_started_too_early")
    return delay


class PaperCanaryWorkflow:
    def __init__(
        self,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.settings = settings
        self.runtime = PaperRuntimeStore(settings.shadow_db_path)
        self.repository = PaperExecutionStore(settings.shadow_db_path)
        self.accounts = account_store(settings)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def stage(self) -> StagedCanary:
        authorization = self.runtime.authorization()
        publication = await fresh_startup(self.settings)
        baseline = publication.account_baseline
        if baseline.open_order_fingerprints:
            raise ValueError("unexpected_open_orders")
        quote = await quote_reader(self.settings).read(authorization.instrument_id)
        if not quote.tradable:
            raise ValueError("canary_instrument_not_tradable")
        proposal = build_paper_limit_proposal(
            authorization=authorization,
            account_baseline_id=baseline.baseline_id,
            best_ask=quote.best_ask,
            quote_market_time=quote.market_time,
            quote_received_at=quote.received_at,
        )
        PaperContinuousStore(self.settings.shadow_db_path).publish_proposal(proposal)
        return StagedCanary(authorization=authorization, proposal=proposal)

    def approve(self, staged: StagedCanary, confirmation: str) -> PaperSubmissionApproval:
        expected = expected_approval_text(staged.proposal)
        if confirmation.strip() != expected:
            raise ValueError("exact_approval_text_mismatch")
        now = self._clock()
        effective_to = min(now + timedelta(minutes=2), staged.authorization.submission_window_end)
        approval = build_submission_approval(
            proposal=staged.proposal,
            authorization=staged.authorization,
            confirmed_limit_price=staged.proposal.exact_limit_price,
            approved_at=now,
            effective_to=effective_to,
        )
        PaperContinuousStore(self.settings.shadow_db_path).publish_approval(approval)
        return approval

    async def submit(self, approval: PaperSubmissionApproval) -> ActiveCanary:
        proposal = self.runtime.proposal(approval.proposal_id)
        authorization = self.runtime.authorization(approval.authorization_id)
        baseline = self.runtime.baseline(proposal.account_baseline_id)
        mode_lock = self.runtime.mode_lock(baseline.mode_lock_id)
        account = self.accounts.read_account_snapshot(baseline.account_snapshot_id)
        now = self._clock()
        if now - baseline.created_at > timedelta(minutes=3):
            raise ValueError("paper_account_baseline_stale")
        quote = await quote_reader(self.settings).read(authorization.instrument_id)
        now = self._clock()
        history = tuple(
            snapshot
            for identity in self.runtime.account_snapshot_ids()
            if identity != account.account_snapshot_id
            for snapshot in (self.accounts.read_account_snapshot(identity),)
            if snapshot.account_fingerprint == account.account_fingerprint
        )
        preflight = build_real_paper_preflight(
            authorization=authorization,
            proposal=proposal,
            approval=approval,
            mode_lock=mode_lock,
            baseline=baseline,
            account=account,
            quote_market_time=quote.market_time,
            quote_received_at=quote.received_at,
            quote_tradable=quote.tradable,
            now=now,
            account_drawdown=account_drawdown(account, history),
        )
        self.runtime.publish_preflight(
            preflight,
            authorization_id=authorization.authorization_id,
            proposal_id=proposal.proposal_id,
        )
        if preflight.blocker_codes:
            raise ValueError("preflight:" + ",".join(preflight.blocker_codes))
        plan = build_paper_canary_order_plan(
            authorization=authorization,
            approval=approval,
            preflight=preflight,
        )
        intent = self.repository.intent_for_order_plan(plan.order_plan_id)
        if intent is None:
            intent = build_paper_intent(
                order_plan=plan,
                line_id="paper-canary-line:" + approval.approval_id[-16:],
                instrument_id=authorization.instrument_id,
                side=authorization.side,
                quantity=authorization.quantity,
                limit_price=approval.exact_limit_price,
                preflight=preflight,
                created_at=approval.approved_at,
            )
        projection = await self._service().submit_once(
            intent=intent,
            authorization=authorization,
            proposal=proposal,
            approval=approval,
            fresh_best_ask=quote.best_ask,
            quote_market_time=quote.market_time,
            now=now,
        )
        return ActiveCanary(approval=approval, intent=intent, projection=projection)

    def latest_active(self) -> ActiveCanary:
        approval = self.runtime.approval()
        intent = self.repository.latest_intent()
        self._validate_scope(intent, approval)
        projection = self.repository.latest_projection(intent.intent_id)
        if projection is None:
            projection = initial_paper_projection(intent)
            self.repository.publish_projection(projection)
        return ActiveCanary(approval=approval, intent=intent, projection=projection)

    async def refresh(self, active: ActiveCanary) -> ActiveCanary:
        projection = (
            await self._service().recover(active.intent)
            if active.projection.recovery_required
            else await self._service().refresh(active.intent)
        )
        return ActiveCanary(active.approval, active.intent, projection)

    async def cancel(self, active: ActiveCanary) -> ActiveCanary:
        projection = await self._service().cancel(
            intent=active.intent,
            approval=active.approval,
        )
        return ActiveCanary(active.approval, active.intent, projection)

    async def settle(self, active: ActiveCanary) -> PaperConvergenceReport:
        refreshed = await self.refresh(active)
        publication = await fresh_startup(self.settings)
        proposal = self.runtime.proposal(active.approval.proposal_id)
        starting_baseline = self.runtime.baseline(proposal.account_baseline_id)
        starting = self.accounts.read_account_snapshot(starting_baseline.account_snapshot_id)
        report = build_convergence_report(
            intent_id=active.intent.intent_id,
            instrument_id=active.intent.instrument_id,
            starting=starting,
            ending=publication.account_snapshot,
            projection=refreshed.projection,
            created_at=self._clock(),
        )
        self.runtime.publish_convergence(report)
        return report

    def _service(self) -> ContinuousPaperExecutionService:
        return ContinuousPaperExecutionService(
            repository=self.repository,
            commands=PaperContinuousStore(self.settings.shadow_db_path),
            gateway=paper_gateway(self.settings),
        )

    def _validate_scope(
        self,
        intent: PaperOrderIntent,
        approval: PaperSubmissionApproval,
    ) -> None:
        proposal = self.runtime.proposal(approval.proposal_id)
        authorization = self.runtime.authorization(approval.authorization_id)
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


__all__ = [
    "ActiveCanary",
    "PaperCanaryWorkflow",
    "StagedCanary",
    "expected_approval_text",
    "workflow_start_delay",
]
