"""Small, explicit application composition root."""

import platform
import sqlite3

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from . import __version__
from .config import Settings, get_settings
from .market_regime.public import FilesystemRotationStore, MarketRotationSnapshot


class DependencyStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    python: str
    duckdb: str
    sqlite: str


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    service: str
    version: str
    mode: str
    status: str
    dependencies: DependencyStatus
    broker_enabled: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    app = FastAPI(title="AstraMind OS Mini", version=__version__)
    origins = [
        f"http://127.0.0.1:{resolved.web_port}",
        f"http://localhost:{resolved.web_port}",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    @app.get("/healthz", response_model=HealthResponse)
    def healthz() -> HealthResponse:
        return HealthResponse(
            service="astramind-os-mini-api",
            version=__version__,
            mode=resolved.environment,
            status="ready",
            dependencies=DependencyStatus(
                python=platform.python_version(),
                duckdb=duckdb.__version__,
                sqlite=sqlite3.sqlite_version,
            ),
            broker_enabled=False,
        )

    @app.get(
        "/api/market/industry-rotation",
        response_model=MarketRotationSnapshot,
        responses={404: {"description": "尚无正式轮动快照"}},
    )
    def industry_rotation() -> MarketRotationSnapshot:
        try:
            return FilesystemRotationStore(resolved.rotation_data_dir).get_current()
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "rotation_snapshot_not_available"},
            ) from error
        except (ValueError, OSError) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "rotation_snapshot_invalid"},
            ) from error

    return app


__all__ = ["HealthResponse", "create_app"]
