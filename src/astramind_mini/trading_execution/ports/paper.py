"""Broker-neutral ports for Paper evidence lookup and append-only storage."""

from __future__ import annotations

from typing import Protocol

from ..contracts.paper import (
    PaperBrokerObservation,
    PaperOrderIntent,
    PaperOrderProjection,
)
from ..contracts.paper_canary import PaperCanaryAuthorization
from ..contracts.paper_continuous import (
    PaperBrokerCommandResult,
    PaperLimitProposal,
    PaperSubmissionApproval,
)


class PaperEvidenceGateway(Protocol):
    def lookup_by_idempotency_key(
        self, intent: PaperOrderIntent
    ) -> tuple[PaperBrokerObservation, ...]: ...


class PaperCommandGateway(Protocol):
    def send_limit_intent(self, intent: PaperOrderIntent) -> None: ...

    def request_cancel(self, intent: PaperOrderIntent) -> None: ...


class ContinuousPaperGateway(Protocol):
    async def query(self, intent: PaperOrderIntent) -> PaperBrokerCommandResult: ...

    async def submit(
        self,
        *,
        intent: PaperOrderIntent,
        authorization: PaperCanaryAuthorization,
        proposal: PaperLimitProposal,
        approval: PaperSubmissionApproval,
        fresh_best_ask: float,
        quote_market_time: object,
        now: object,
    ) -> PaperBrokerCommandResult: ...

    async def cancel(
        self,
        *,
        intent: PaperOrderIntent,
        approval: PaperSubmissionApproval,
    ) -> PaperBrokerCommandResult: ...


class PaperExecutionRepository(Protocol):
    def publish_intent(self, value: PaperOrderIntent) -> None: ...

    def append_observation(self, value: PaperBrokerObservation) -> None: ...

    def observations_for(self, intent_id: str) -> tuple[PaperBrokerObservation, ...]: ...

    def publish_projection(self, value: PaperOrderProjection) -> None: ...

    def latest_projection(self, intent_id: str) -> PaperOrderProjection | None: ...


class PaperCommandEvidenceStore(Protocol):
    def append_command(self, value: PaperBrokerCommandResult) -> None: ...


__all__ = [
    "ContinuousPaperGateway",
    "PaperCommandEvidenceStore",
    "PaperCommandGateway",
    "PaperEvidenceGateway",
    "PaperExecutionRepository",
]
