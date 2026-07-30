"""FastAPI boundary for the read-only canonical stock workbench."""

import sqlite3
from datetime import date
from typing import Literal, Protocol

import duckdb
from fastapi import FastAPI, HTTPException

from astramind_mini.config import Settings
from astramind_mini.data.public import RealtimeInstrumentProjection, RealtimeMinuteBar

from .price_history_api import register_price_history_route
from .public import (
    SnapshotStockWorkbench,
    StockRealtimeMarketOverlay,
    StockWorkbenchProjection,
)


class RealtimeStockOverlayReader(Protocol):
    def current_instruments(self) -> RealtimeInstrumentProjection: ...

    def minute_bars(
        self,
        *,
        instrument_id: str,
        market_date: date,
    ) -> tuple[RealtimeMinuteBar, ...]: ...


def register_stock_workbench_route(
    app: FastAPI,
    settings: Settings,
    realtime_store: RealtimeStockOverlayReader,
) -> None:
    register_price_history_route(app, settings)

    @app.get(
        "/api/market/stocks/{instrument_id}",
        response_model=StockWorkbenchProjection,
        responses={404: {"description": "证券或数据快照不可用"}},
    )
    def stock_workbench(
        instrument_id: str,
        origin: Literal[
            "watchlist",
            "industry_rotation",
            "industry_lifecycle",
            "industry_ranking",
            "strategy_candidate",
            "portfolio_holding",
            "attention_case",
        ] = "watchlist",
        mode: Literal[
            "current",
            "completed",
            "historical_replay",
            "sealed_evidence",
        ] = "current",
        return_target: Literal[
            "market_stocks",
            "industry_rotation",
            "industry_lifecycle",
            "industry_ranking",
            "strategy_arena",
            "portfolio",
            "today",
        ] = "market_stocks",
        data_snapshot_id: str | None = None,
        as_of: date | None = None,
        industry_code: str | None = None,
    ) -> StockWorkbenchProjection:
        try:
            reader = SnapshotStockWorkbench(settings.data_dir)
            projection = (
                reader.current(
                    instrument_id.upper(),
                    origin=origin,
                    mode=mode,
                    return_target=return_target,
                    industry_code=industry_code,
                )
                if data_snapshot_id is None
                else reader.load(
                    instrument_id.upper(),
                    data_snapshot_id=data_snapshot_id,
                    as_of=as_of,
                    origin=origin,
                    mode=mode,
                    return_target=return_target,
                    industry_code=industry_code,
                )
            )
            return (
                projection
                if mode in ("historical_replay", "sealed_evidence")
                else _with_realtime_overlay(projection, realtime_store)
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "stock_workbench_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error, duckdb.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "stock_workbench_projection_unavailable"},
            ) from error


def _with_realtime_overlay(
    projection: StockWorkbenchProjection,
    store: RealtimeStockOverlayReader,
) -> StockWorkbenchProjection:
    try:
        current = store.current_instruments()
        quote = next(
            item for item in current.quotes if item.instrument_id == projection.focus.instrument_id
        )
    except (FileNotFoundError, StopIteration):
        return projection
    overlay = StockRealtimeMarketOverlay(
        state=current.state,
        provider=current.provider,
        session_id=current.session_id,
        as_of=current.as_of,
        quote=quote,
        minutes=store.minute_bars(
            instrument_id=quote.instrument_id,
            market_date=current.market_date,
        ),
        known_gaps=current.known_gaps,
    )
    return projection.model_copy(update={"realtime_market_overlay": overlay})


__all__ = ["register_stock_workbench_route"]
