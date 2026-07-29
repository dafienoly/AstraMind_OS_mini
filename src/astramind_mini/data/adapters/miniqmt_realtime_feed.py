"""Realtime feed adapter backed by the persistent MiniQMT data bridge."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from ..contracts.realtime import RealtimeQuoteObservation
from ..contracts.source import SourceHealth
from .miniqmt_bridge import MiniQMTBridgeClient
from .miniqmt_l1 import normalize_l1_messages
from .miniqmt_source import MiniQMTSourceAdapter


class MiniQMTRealtimeFeed:
    def __init__(self, bridge: MiniQMTBridgeClient) -> None:
        self._bridge = bridge
        self._latest: dict[str, RealtimeQuoteObservation] = {}

    async def subscribe(
        self, universe: tuple[str, ...]
    ) -> AsyncIterator[tuple[RealtimeQuoteObservation, ...]]:
        markets = universe or ("SH", "SZ", "BJ")
        await self._bridge.request("subscribe", markets=markets)
        async for event in self._bridge.quote_events():
            payload = event.get("payload")
            received_at = datetime.fromisoformat(str(event["received_at"]))
            rows, _ = normalize_l1_messages([payload], received_at)
            for row in rows:
                self._latest[row.instrument_id] = row
            yield rows

    async def unsubscribe(self) -> None:
        await self._bridge.request("unsubscribe")

    async def snapshot(self) -> tuple[RealtimeQuoteObservation, ...]:
        return tuple(self._latest[key] for key in sorted(self._latest))

    async def health(self) -> SourceHealth:
        return await MiniQMTSourceAdapter(self._bridge).health()


__all__ = ["MiniQMTRealtimeFeed"]
