"""FastAPI route for snapshot-pinned complete price history."""

import sqlite3
from datetime import date
from typing import Literal

import duckdb
from fastapi import FastAPI, HTTPException, Query

from astramind_mini.config import Settings

from .adapters.price_history import SnapshotPriceHistory
from .contracts.price_history import PriceHistoryPage


def register_price_history_route(app: FastAPI, settings: Settings) -> None:
    @app.get(
        "/api/market/history/{instrument_type}/{instrument_id}",
        response_model=PriceHistoryPage,
        responses={404: {"description": "证券或快照历史不可用"}},
    )
    def price_history(
        instrument_type: Literal["stock", "index", "etf"],
        instrument_id: str,
        window: Literal["one_year", "five_years", "listed_since"] = "one_year",
        data_snapshot_id: str | None = None,
        evidence_cutoff: date | None = None,
        start: date | None = None,
        end: date | None = None,
        cursor: date | None = None,
        page_size: int = Query(default=520, ge=1, le=1000),
    ) -> PriceHistoryPage:
        try:
            reader = SnapshotPriceHistory(settings.data_dir)
            if data_snapshot_id is None:
                return reader.current(
                    instrument_type,
                    instrument_id.upper(),
                    window=window,
                    evidence_cutoff=evidence_cutoff,
                    start=start,
                    end=end,
                    cursor=cursor,
                    page_size=page_size,
                )
            return reader.load(
                data_snapshot_id,
                instrument_type,
                instrument_id.upper(),
                window=window,
                evidence_cutoff=evidence_cutoff,
                start=start,
                end=end,
                cursor=cursor,
                page_size=page_size,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "price_history_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error, duckdb.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "price_history_projection_unavailable"},
            ) from error


__all__ = ["register_price_history_route"]
