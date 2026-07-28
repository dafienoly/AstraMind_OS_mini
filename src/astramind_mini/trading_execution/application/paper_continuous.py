"""Recoverable orchestration for authorized continuous Paper execution."""

from __future__ import annotations

from datetime import datetime

from astramind_mini.contracts import ExecutionEvent, ExecutionMode

from ..contracts.paper import (
    PaperBrokerObservation,
    PaperObservationKind,
    PaperOrderIntent,
    PaperOrderProjection,
)
from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import (
    PaperBrokerCommandResult,
    PaperLimitProposal,
    PaperSubmissionApproval,
)
from ..domain.paper import initial_paper_projection, replay_paper_observations
from ..domain.reconciliation import canonical_hash
from ..ports.paper import (
    ContinuousPaperGateway,
    PaperCommandEvidenceStore,
    PaperExecutionRepository,
)


class ContinuousPaperExecutionService:
    def __init__(
        self,
        *,
        repository: PaperExecutionRepository,
        commands: PaperCommandEvidenceStore,
        gateway: ContinuousPaperGateway,
    ) -> None:
        self._repository = repository
        self._commands = commands
        self._gateway = gateway

    async def submit_once(
        self,
        *,
        intent: PaperOrderIntent,
        authorization: PaperCanaryAuthorization,
        proposal: PaperLimitProposal,
        approval: PaperSubmissionApproval,
        fresh_best_ask: float,
        quote_market_time: datetime,
        now: datetime,
    ) -> PaperOrderProjection:
        current = self._repository.latest_projection(intent.intent_id)
        self._prepare(intent)
        existing = await self._gateway.query(intent)
        self._commands.append_command(existing)
        if existing.outcome == "existing":
            return self._record_result(intent, existing)
        if current is not None and current.state != "prepared":
            return self._record_result(intent, existing)
        if existing.outcome != "not_found":
            raise ValueError("Paper 幂等查询返回不可提交状态")
        try:
            result = await self._gateway.submit(
                intent=intent,
                authorization=authorization,
                proposal=proposal,
                approval=approval,
                fresh_best_ask=fresh_best_ask,
                quote_market_time=quote_market_time,
                now=now,
            )
        except (OSError, RuntimeError, TimeoutError):
            return self._record_unknown(intent, now)
        self._commands.append_command(result)
        return self._record_result(intent, result)

    async def recover(self, intent: PaperOrderIntent) -> PaperOrderProjection:
        current = self._repository.latest_projection(intent.intent_id)
        if current is None or not current.recovery_required:
            raise ValueError("只有 submission_unknown 允许执行恢复查询")
        result = await self._gateway.query(intent)
        self._commands.append_command(result)
        return self._record_result(intent, result)

    async def refresh(self, intent: PaperOrderIntent) -> PaperOrderProjection:
        current = self._repository.latest_projection(intent.intent_id)
        if current is None:
            raise ValueError("Paper 意图尚无本地投影")
        result = await self._gateway.query(intent)
        self._commands.append_command(result)
        return self._record_result(intent, result)

    async def cancel(
        self,
        *,
        intent: PaperOrderIntent,
        approval: PaperSubmissionApproval,
    ) -> PaperOrderProjection:
        current = self._repository.latest_projection(intent.intent_id)
        if current is None or current.state not in {"acknowledged", "partially_filled"}:
            raise ValueError("只有已确认且未终结的本次金丝雀允许撤单")
        result = await self._gateway.cancel(intent=intent, approval=approval)
        self._commands.append_command(result)
        return self._record_result(intent, result)

    def _prepare(self, intent: PaperOrderIntent) -> None:
        self._repository.publish_intent(intent)
        if self._repository.latest_projection(intent.intent_id) is None:
            self._repository.publish_projection(initial_paper_projection(intent))

    def _record_result(
        self, intent: PaperOrderIntent, result: PaperBrokerCommandResult
    ) -> PaperOrderProjection:
        observation = _observation(
            intent,
            result,
            sequence=len(self._repository.observations_for(intent.intent_id)) + 1,
        )
        existing = self._repository.observations_for(intent.intent_id)
        projection = replay_paper_observations(intent, (*existing, observation))
        self._repository.append_observation(observation)
        self._repository.publish_projection(projection)
        return projection

    def _record_unknown(
        self, intent: PaperOrderIntent, occurred_at: datetime
    ) -> PaperOrderProjection:
        digest = canonical_hash(
            {"intent_id": intent.intent_id, "kind": "submission_unknown", "at": occurred_at}
        )
        result = PaperBrokerCommandResult(
            command_id="paper-broker-command:" + digest[7:],
            intent_id=intent.intent_id,
            action="submit",
            outcome="unknown",
            broker_order_fingerprint=None,
            broker_status_code="submission_unknown",
            cumulative_filled_quantity=0,
            observed_at=occurred_at,
            content_hash=digest,
        )
        self._commands.append_command(result)
        observation = _observation(
            intent,
            result,
            sequence=len(self._repository.observations_for(intent.intent_id)) + 1,
            forced_kind=PaperObservationKind.SUBMISSION_UNKNOWN,
        )
        existing = self._repository.observations_for(intent.intent_id)
        projection = replay_paper_observations(intent, (*existing, observation))
        self._repository.append_observation(observation)
        self._repository.publish_projection(projection)
        return projection


def _observation(
    intent: PaperOrderIntent,
    result: PaperBrokerCommandResult,
    *,
    sequence: int,
    forced_kind: PaperObservationKind | None = None,
) -> PaperBrokerObservation:
    kind = forced_kind or _kind(result, intent.quantity)
    event_payload = {
        "intent_id": intent.intent_id,
        "command_id": result.command_id,
        "kind": kind,
        "sequence": sequence,
    }
    event_hash = canonical_hash(event_payload)
    event = ExecutionEvent(
        execution_event_id="paper-event:" + event_hash[7:],
        order_plan_id=intent.order_plan.order_plan_id,
        execution_mode=ExecutionMode.PAPER,
        event_type=f"paper_{kind}",
        sequence=sequence,
        occurred_at=result.observed_at,
        content_hash=event_hash,
    )
    payload = {
        "intent_id": intent.intent_id,
        "command_id": result.command_id,
        "kind": kind,
        "event": event,
    }
    digest = canonical_hash(payload)
    return PaperBrokerObservation(
        evidence_id="paper-evidence:" + digest[7:],
        intent_id=intent.intent_id,
        idempotency_key=intent.idempotency_key,
        execution_event=event,
        kind=kind,
        cumulative_filled_quantity=result.cumulative_filled_quantity,
        average_fill_price=result.average_fill_price,
        broker_order_fingerprint=result.broker_order_fingerprint,
        source="broker_query",
        received_at=result.observed_at,
        content_hash=digest,
    )


def _kind(result: PaperBrokerCommandResult, requested_quantity: int) -> PaperObservationKind:
    if result.outcome == "unknown":
        return PaperObservationKind.SUBMISSION_UNKNOWN
    if result.broker_status_code in {"52", "53", "54"}:
        return PaperObservationKind.CANCELLED
    if result.broker_status_code == "56":
        return PaperObservationKind.REJECTED
    if result.action == "cancel" and result.outcome == "cancel_requested":
        return PaperObservationKind.CANCEL_REQUESTED
    if result.outcome == "rejected":
        return PaperObservationKind.REJECTED
    if result.outcome == "not_found":
        return PaperObservationKind.RECOVERY_NOT_FOUND
    if result.cumulative_filled_quantity >= requested_quantity:
        return PaperObservationKind.FILLED
    if result.cumulative_filled_quantity:
        return PaperObservationKind.PARTIAL_FILL
    return PaperObservationKind.ACKNOWLEDGED


__all__ = ["ContinuousPaperExecutionService"]
