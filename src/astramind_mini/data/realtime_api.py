"""Read-only current projection and SSE routes for the market interface."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .adapters.market_session_context import SnapshotMarketSessionContext
from .adapters.realtime_projection_store import RealtimeProjectionStore
from .adapters.realtime_watchlist_store import RealtimeWatchlistStore
from .application.identity import content_hash
from .application.market_session_status import (
    SHANGHAI,
    MarketSessionContext,
    enrich_market_projection,
)
from .application.realtime_indicators import (
    RealtimeIndicatorPoint,
    compute_realtime_indicators,
)
from .application.realtime_minutes import incomplete_bucket_gaps
from .contracts.realtime_projection import (
    RealtimeInstrumentProjection,
    RealtimeInstrumentQuote,
    RealtimeMarketProjection,
    RealtimeMinuteBar,
)

SSE_POLL_SECONDS = 1.0


class WatchlistPayload(BaseModel):
    instrument_ids: tuple[str, ...] = Field(default=(), max_length=100)


class RealtimeInstrumentDetail(BaseModel):
    projection_id: str
    provider: str
    session_id: str
    state: str
    as_of: datetime
    quote: RealtimeInstrumentQuote
    minutes: tuple[RealtimeMinuteBar, ...]
    known_gaps: tuple[str, ...] = ()


class RealtimeInstrumentSearchResult(BaseModel):
    instrument_id: str
    instrument_name: str | None
    instrument_type: str
    last_price: float | None
    change_percent: float | None
    status_label: str


class RealtimeBarWindow(BaseModel):
    instrument_id: str
    frequency_minutes: int
    start_date: date
    end_date: date
    sessions: tuple[date, ...]
    bars: tuple[RealtimeMinuteBar, ...]
    indicators: tuple[RealtimeIndicatorPoint, ...]
    indicator_state: str
    known_gaps: tuple[str, ...] = ()
    next_cursor: str | None = None


def register_realtime_routes(app: FastAPI, data_root: Path) -> None:
    store = RealtimeProjectionStore(data_root)
    session_context = SnapshotMarketSessionContext(data_root)
    watchlist = RealtimeWatchlistStore(data_root.parent / "control")
    _register_instrument_routes(app, store)
    _register_watchlist_routes(app, watchlist)

    @app.get(
        "/api/market/realtime",
        response_model=RealtimeMarketProjection,
        responses={404: {"description": "尚无 MiniQMT 实时投影"}},
    )
    def realtime_current() -> RealtimeMarketProjection:
        try:
            now = datetime.now(UTC)
            return _freshness(
                store.current(),
                now,
                context=session_context.read_if_available(today=now.astimezone(SHANGHAI).date()),
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "realtime_projection_not_available"},
            ) from error
        except (ValueError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "realtime_projection_invalid"},
            ) from error

    @app.get("/api/market/realtime/stream")
    async def realtime_stream(request: Request) -> StreamingResponse:
        return StreamingResponse(
            _events(store, request, session_context),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )


def _register_instrument_routes(
    app: FastAPI,
    store: RealtimeProjectionStore,
) -> None:
    @app.get("/api/market/realtime/instruments", response_model=RealtimeInstrumentProjection)
    def realtime_instruments(
        instrument_ids: str | None = Query(default=None),
        industry_code: str | None = Query(default=None),
        instrument_type: str | None = Query(default=None),
    ) -> RealtimeInstrumentProjection:
        try:
            projection = _instrument_freshness(store.current_instruments(), datetime.now(UTC))
        except FileNotFoundError as error:
            raise HTTPException(
                404,
                detail={"code": "realtime_instruments_not_available"},
            ) from error
        selected = {
            code.strip().upper() for code in (instrument_ids or "").split(",") if code.strip()
        }
        quotes = tuple(
            quote
            for quote in projection.quotes
            if (not selected or quote.instrument_id in selected)
            and (industry_code is None or quote.industry_code == industry_code)
            and (instrument_type is None or quote.instrument_type == instrument_type)
        )
        return projection.model_copy(update={"quotes": quotes[:500], "open_minutes": ()})

    @app.get(
        "/api/market/realtime/instruments/search",
        response_model=tuple[RealtimeInstrumentSearchResult, ...],
    )
    def realtime_instrument_search(
        q: str = Query(min_length=1, max_length=32),
        limit: int = Query(default=12, ge=1, le=20),
    ) -> tuple[RealtimeInstrumentSearchResult, ...]:
        try:
            projection = _instrument_freshness(store.current_instruments(), datetime.now(UTC))
        except FileNotFoundError as error:
            raise HTTPException(
                404,
                detail={"code": "realtime_instruments_not_available"},
            ) from error
        needle = q.strip().casefold()
        ranked = sorted(
            (
                (_search_rank(quote, needle), quote)
                for quote in projection.quotes
                if _search_rank(quote, needle) is not None
            ),
            key=lambda item: (item[0], item[1].instrument_id),
        )
        return tuple(
            RealtimeInstrumentSearchResult(
                instrument_id=quote.instrument_id,
                instrument_name=quote.instrument_name,
                instrument_type=quote.instrument_type,
                last_price=quote.last_price,
                change_percent=quote.change_percent,
                status_label=quote.status_label,
            )
            for _, quote in ranked[:limit]
        )

    @app.get("/api/market/realtime/instruments/stream")
    async def realtime_instrument_stream(
        request: Request,
        instrument_ids: str = Query(min_length=1),
    ) -> StreamingResponse:
        selected = frozenset(
            code.strip().upper() for code in instrument_ids.split(",") if code.strip()
        )
        return StreamingResponse(
            _instrument_events(store, selected, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    _register_bar_routes(app, store)

    @app.get(
        "/api/market/realtime/instruments/{instrument_id}",
        response_model=RealtimeInstrumentDetail,
    )
    def realtime_instrument_detail(instrument_id: str) -> RealtimeInstrumentDetail:
        try:
            projection = _instrument_freshness(store.current_instruments(), datetime.now(UTC))
            quote = next(
                item for item in projection.quotes if item.instrument_id == instrument_id.upper()
            )
            minutes = store.minute_bars(
                instrument_id=quote.instrument_id,
                market_date=projection.market_date,
            )
        except (FileNotFoundError, StopIteration) as error:
            raise HTTPException(
                404,
                detail={"code": "realtime_instrument_not_available"},
            ) from error
        return RealtimeInstrumentDetail(
            projection_id=projection.projection_id,
            provider=projection.provider,
            session_id=projection.session_id,
            state=projection.state,
            as_of=projection.as_of,
            quote=quote,
            minutes=minutes,
            known_gaps=projection.known_gaps,
        )


def _register_bar_routes(app: FastAPI, store: RealtimeProjectionStore) -> None:
    @app.get(
        "/api/market/realtime/instruments/{instrument_id}/bars",
        response_model=RealtimeBarWindow,
    )
    def realtime_instrument_bars(
        instrument_id: str,
        frequency: int = 1,
        start_date: date | None = None,
        end_date: date | None = None,
        recent_sessions: int = 1,
    ) -> RealtimeBarWindow:
        if frequency not in {1, 5, 15, 30, 60, 120}:
            raise HTTPException(422, detail={"code": "unsupported_realtime_frequency"})
        if not 1 <= recent_sessions <= 5:
            raise HTTPException(422, detail={"code": "invalid_recent_session_count"})
        available = store.available_market_dates()
        if not available:
            raise HTTPException(404, detail={"code": "realtime_minutes_not_available"})
        resolved_end = end_date or available[-1]
        eligible = tuple(value for value in available if value <= resolved_end)
        selected = (
            tuple(value for value in eligible if start_date <= value)
            if start_date is not None
            else eligible[-recent_sessions:]
        )
        if not selected or len(selected) > 5:
            raise HTTPException(
                422,
                detail={"code": "realtime_date_window_exceeds_five_sessions"},
            )
        source_minutes = store.history_bars(
            instrument_id=instrument_id.upper(),
            frequency=1,
            start_date=selected[0],
            end_date=selected[-1],
        )
        bars = store.history_bars(
            instrument_id=instrument_id.upper(),
            frequency=frequency,
            start_date=selected[0],
            end_date=selected[-1],
        )
        seed_sessions = eligible[-5:]
        calculation_bars = store.history_bars(
            instrument_id=instrument_id.upper(),
            frequency=frequency,
            start_date=seed_sessions[0],
            end_date=selected[-1],
        )
        all_indicators, indicator_state = compute_realtime_indicators(calculation_bars)
        indicators = tuple(point for point in all_indicators if point.minute.date() >= selected[0])
        cursor = content_hash(
            {
                "instrument_id": instrument_id.upper(),
                "frequency": frequency,
                "sessions": selected,
                "last": bars[-1].source_identity if bars else None,
            }
        )
        return RealtimeBarWindow(
            instrument_id=instrument_id.upper(),
            frequency_minutes=frequency,
            start_date=selected[0],
            end_date=selected[-1],
            sessions=selected,
            bars=bars,
            indicators=indicators,
            indicator_state=indicator_state,
            known_gaps=incomplete_bucket_gaps(source_minutes, frequency),
            next_cursor=cursor,
        )


def _register_watchlist_routes(
    app: FastAPI,
    watchlist: RealtimeWatchlistStore,
) -> None:
    @app.get("/api/market/watchlist", response_model=WatchlistPayload)
    def get_watchlist() -> WatchlistPayload:
        return WatchlistPayload(instrument_ids=watchlist.read())

    @app.put("/api/market/watchlist", response_model=WatchlistPayload)
    def put_watchlist(payload: WatchlistPayload) -> WatchlistPayload:
        invalid = [code for code in payload.instrument_ids if len(code) > 16 or "." not in code]
        if invalid:
            raise HTTPException(422, detail={"code": "invalid_instrument_id", "values": invalid})
        return WatchlistPayload(instrument_ids=watchlist.write(payload.instrument_ids))


async def _events(
    store: RealtimeProjectionStore,
    request: Request | None = None,
    session_context: SnapshotMarketSessionContext | None = None,
) -> AsyncIterator[str]:
    last_id = ""
    last_heartbeat = datetime.now(UTC)
    while True:
        if request is not None and await request.is_disconnected():
            return
        now = datetime.now(UTC)
        try:
            projection = _freshness(
                await asyncio.to_thread(store.current),
                now,
                context=(
                    await asyncio.to_thread(
                        session_context.read_if_available,
                        today=now.astimezone(SHANGHAI).date(),
                    )
                    if session_context is not None
                    else None
                ),
            )
            identity = (
                f"{projection.projection_id}:{projection.state}:"
                f"{projection.operational_state}:{projection.daily_data_state}"
            )
            if identity != last_id:
                payload = json.dumps(
                    projection.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {projection.projection_id}\nevent: market\ndata: {payload}\n\n"
                last_id = identity
        except FileNotFoundError:
            if last_id != "disconnected":
                payload = json.dumps(
                    {
                        "provider": "miniqmt",
                        "state": "disconnected",
                        "as_of": now.isoformat(),
                        "known_gaps": ["realtime_projection_not_available"],
                    },
                    separators=(",", ":"),
                )
                yield f"event: status\ndata: {payload}\n\n"
                last_id = "disconnected"
        if now - last_heartbeat >= timedelta(seconds=5):
            yield f": heartbeat {now.isoformat()}\n\n"
            last_heartbeat = now
        await asyncio.sleep(SSE_POLL_SECONDS)


async def _instrument_events(
    store: RealtimeProjectionStore,
    selected: frozenset[str],
    request: Request | None = None,
) -> AsyncIterator[str]:
    last_id = ""
    while True:
        if request is not None and await request.is_disconnected():
            return
        try:
            projection = _instrument_freshness(
                await asyncio.to_thread(store.current_instruments),
                datetime.now(UTC),
            )
            quotes = tuple(quote for quote in projection.quotes if quote.instrument_id in selected)
            identity = f"{projection.projection_id}:{projection.state}"
            if identity != last_id:
                payload = projection.model_copy(
                    update={
                        "quotes": quotes,
                        "open_minutes": tuple(
                            row for row in projection.open_minutes if row.instrument_id in selected
                        ),
                    }
                )
                value = json.dumps(
                    payload.model_dump(mode="json"),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                yield f"id: {projection.projection_id}\nevent: instruments\ndata: {value}\n\n"
                last_id = identity
        except FileNotFoundError:
            yield 'event: status\ndata: {"state":"disconnected"}\n\n'
        await asyncio.sleep(SSE_POLL_SECONDS)


def _freshness(
    projection: RealtimeMarketProjection,
    now: datetime,
    *,
    context: MarketSessionContext | None = None,
) -> RealtimeMarketProjection:
    return enrich_market_projection(projection, now=now, context=context)


def _instrument_freshness(
    projection: RealtimeInstrumentProjection,
    now: datetime,
) -> RealtimeInstrumentProjection:
    latest = max((quote.received_at for quote in projection.quotes), default=None)
    if projection.state == "disconnected":
        return projection.model_copy(update={"as_of": now})
    if latest is None or now - latest > timedelta(seconds=10):
        return projection.model_copy(update={"state": "stale", "as_of": now})
    return projection


def _search_rank(
    quote: RealtimeInstrumentQuote,
    needle: str,
) -> int | None:
    code = quote.instrument_id.casefold()
    bare_code = code.split(".", 1)[0]
    name = (quote.instrument_name or "").casefold()
    if bare_code.startswith(needle) or code.startswith(needle):
        return 0
    if name.startswith(needle):
        return 1
    if needle in bare_code or needle in code:
        return 2
    if needle in name:
        return 3
    return None


__all__ = ["register_realtime_routes"]
