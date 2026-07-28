"""Synthetic-only Paper adapter used to prove the port without a broker session."""

from __future__ import annotations

from ..contracts.paper import PaperBrokerObservation, PaperOrderIntent


class OfflinePaperGateway:
    def __init__(self, observations: tuple[PaperBrokerObservation, ...] = ()) -> None:
        self._observations = observations
        self.lookup_count = 0
        self.command_attempt_count = 0

    def lookup_by_idempotency_key(
        self, intent: PaperOrderIntent
    ) -> tuple[PaperBrokerObservation, ...]:
        self.lookup_count += 1
        return tuple(
            item for item in self._observations if item.idempotency_key == intent.idempotency_key
        )

    def send_limit_intent(self, intent: PaperOrderIntent) -> None:
        self.command_attempt_count += 1
        raise PermissionError("WP-0016 只允许离线合同验证，Paper 写入未授权")

    def request_cancel(self, intent: PaperOrderIntent) -> None:
        self.command_attempt_count += 1
        raise PermissionError("WP-0016 只允许离线合同验证，Paper 撤单未授权")


__all__ = ["OfflinePaperGateway"]
