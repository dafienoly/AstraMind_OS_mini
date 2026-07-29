"""Ports for interchangeable batch sources and realtime market feeds."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from ..contracts.realtime import RealtimeQuoteObservation
from ..contracts.source import (
    CanonicalDatasetRequest,
    ProviderBatch,
    SourceHealth,
)


class BatchDataSourceAdapter(Protocol):
    @property
    def provider_id(self) -> str: ...

    async def capabilities(self) -> frozenset[str]: ...

    async def fetch(self, request: CanonicalDatasetRequest) -> ProviderBatch: ...

    async def health(self) -> SourceHealth: ...


class RealtimeMarketFeedAdapter(Protocol):
    async def subscribe(
        self, universe: tuple[str, ...]
    ) -> AsyncIterator[tuple[RealtimeQuoteObservation, ...]]: ...

    async def unsubscribe(self) -> None: ...

    async def snapshot(self) -> tuple[RealtimeQuoteObservation, ...]: ...

    async def health(self) -> SourceHealth: ...


__all__ = ["BatchDataSourceAdapter", "RealtimeMarketFeedAdapter"]
