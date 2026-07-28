"""Offline Paper orchestration; deliberately contains no command submission path."""

from __future__ import annotations

from ..contracts.paper import (
    PaperBrokerObservation,
    PaperOrderIntent,
    PaperOrderProjection,
)
from ..domain.paper import initial_paper_projection, replay_paper_observations
from ..ports.paper import PaperEvidenceGateway, PaperExecutionRepository


class OfflinePaperExecutionService:
    def __init__(
        self,
        repository: PaperExecutionRepository,
        evidence_gateway: PaperEvidenceGateway,
    ) -> None:
        self._repository = repository
        self._evidence_gateway = evidence_gateway

    def prepare(self, intent: PaperOrderIntent) -> PaperOrderProjection:
        self._repository.publish_intent(intent)
        projection = initial_paper_projection(intent)
        self._repository.publish_projection(projection)
        return projection

    def record(
        self,
        intent: PaperOrderIntent,
        observation: PaperBrokerObservation,
    ) -> PaperOrderProjection:
        existing = self._repository.observations_for(intent.intent_id)
        projection = replay_paper_observations(intent, (*existing, observation))
        self._repository.append_observation(observation)
        self._repository.publish_projection(projection)
        return projection

    def recover_unknown(self, intent: PaperOrderIntent) -> PaperOrderProjection:
        current = self._repository.latest_projection(intent.intent_id)
        if current is None or not current.recovery_required:
            raise ValueError("只有 submission_unknown 状态允许执行事实恢复")
        observations = self._evidence_gateway.lookup_by_idempotency_key(intent)
        existing = self._repository.observations_for(intent.intent_id)
        projection = replay_paper_observations(intent, (*existing, *observations))
        for observation in observations:
            self._repository.append_observation(observation)
        self._repository.publish_projection(projection)
        return projection


__all__ = ["OfflinePaperExecutionService"]
