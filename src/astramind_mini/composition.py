"""Small, explicit application composition root."""

import platform
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import duckdb
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, model_validator

from . import __version__
from .config import Settings, get_settings
from .data.adapters import DailyPipelineStore, RealtimeProjectionStore
from .data.contracts import DailyPipelineStatus
from .data.realtime_api import register_realtime_routes
from .local_ops.contracts import DailyDecisionStatus
from .local_ops.daily_decision_store import DailyDecisionStore
from .local_ops.daily_operations import (
    DailyOperationsProjection,
    DailyOperationsReader,
)
from .local_ops.daily_scheduler_contracts import DailyRunRequest
from .local_ops.daily_scheduler_store import DailySchedulerStore
from .market_regime.model_status_api import register_market_model_status_route
from .market_regime.public import (
    EtfRotationProjection,
    FilesystemRotationStore,
    IndustryHierarchyView,
    IndustryLifecycleIntradayProjection,
    IndustryLifecycleProjection,
    IndustryResearchRankingSnapshot,
    MarketDashboardProjection,
    MarketRotationSnapshot,
    SnapshotEtfRotation,
    SnapshotIndustryHierarchy,
    SnapshotIndustryLifecycle,
    SnapshotIndustryResearchRanking,
    SnapshotMarketDashboard,
)
from .market_regime.stock_workbench_api import register_stock_workbench_route
from .trading_execution.adapters.paper_operations_reader import PaperOperationsReader
from .trading_execution.contracts.paper_continuous import PaperOperationsSnapshot


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


class DailyRunRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["run", "recover", "retry_provider"]
    target_date: date | None = None
    run_id: str | None = None

    @model_validator(mode="after")
    def require_action_identity(self) -> "DailyRunRequestInput":
        if self.action == "run" and self.target_date is None:
            raise ValueError("run 请求必须提供 target_date")
        if self.action in ("recover", "retry_provider") and self.run_id is None:
            raise ValueError("恢复请求必须提供 run_id")
        return self


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
        allow_methods=["GET", "POST", "PUT"],
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

    _register_etf_routes(app, resolved)
    _register_market_routes(app, resolved)
    register_market_model_status_route(app, resolved.market_model_dir)

    @app.get(
        "/api/execution/paper-operations",
        response_model=PaperOperationsSnapshot,
        responses={503: {"description": "Paper 本地投影不可用"}},
    )
    def paper_operations() -> PaperOperationsSnapshot:
        try:
            return PaperOperationsReader(resolved.shadow_db_path).current()
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "paper_operations_projection_unavailable"},
            ) from error

    _register_system_routes(app, resolved)
    register_realtime_routes(app, resolved.data_dir)
    return app


def _register_etf_routes(app: FastAPI, resolved: Settings) -> None:
    @app.get(
        "/api/market/etf-rotation",
        response_model=EtfRotationProjection,
        responses={404: {"description": "尚无正式 ETF 数据快照"}},
    )
    def etf_rotation(
        data_snapshot_id: str | None = None,
        selected_etf_code: str | None = None,
    ) -> EtfRotationProjection:
        try:
            reader = SnapshotEtfRotation(resolved.data_dir)
            if data_snapshot_id is None:
                return reader.current(selected_etf_code=selected_etf_code)
            return reader.load(
                data_snapshot_id,
                selected_etf_code=selected_etf_code,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "etf_rotation_snapshot_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "etf_rotation_projection_unavailable"},
            ) from error


def _register_market_routes(app: FastAPI, resolved: Settings) -> None:
    _register_lifecycle_routes(app, resolved)
    register_stock_workbench_route(
        app,
        resolved,
        RealtimeProjectionStore(resolved.data_dir),
    )

    @app.get(
        "/api/market/dashboard",
        response_model=MarketDashboardProjection,
        responses={404: {"description": "尚无正式数据快照"}},
    )
    def market_dashboard() -> MarketDashboardProjection:
        try:
            return SnapshotMarketDashboard(resolved.data_dir).current()
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "market_dashboard_snapshot_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "market_dashboard_projection_unavailable"},
            ) from error

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

    @app.get(
        "/api/market/industry-hierarchy",
        response_model=IndustryHierarchyView,
        responses={503: {"description": "行业层级证据不可用"}},
    )
    def industry_hierarchy(
        data_snapshot_id: str,
        as_of: date,
        parent_code: str | None = None,
        l2_code: str | None = None,
        instrument_id: str | None = None,
        all_l2: bool = False,
    ) -> IndustryHierarchyView:
        try:
            return SnapshotIndustryHierarchy(resolved.data_dir).load(
                data_snapshot_id=data_snapshot_id,
                as_of=as_of,
                parent_code=parent_code,
                l2_code=l2_code,
                instrument_id=instrument_id,
                all_l2=all_l2,
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "industry_hierarchy_projection_unavailable"},
            ) from error

    @app.get(
        "/api/market/industry-ranking",
        response_model=IndustryResearchRankingSnapshot,
        responses={404: {"description": "尚无正式数据快照"}},
    )
    def industry_ranking(
        industry_code: str,
        data_snapshot_id: str | None = None,
        instrument_id: str | None = None,
    ) -> IndustryResearchRankingSnapshot:
        try:
            reader = SnapshotIndustryResearchRanking(resolved.data_dir)
            if data_snapshot_id is None:
                return reader.current(
                    industry_code=industry_code,
                    instrument_id=instrument_id,
                )
            return reader.load(
                data_snapshot_id=data_snapshot_id,
                industry_code=industry_code,
                instrument_id=instrument_id,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "industry_ranking_snapshot_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "industry_ranking_projection_unavailable"},
            ) from error


def _register_lifecycle_routes(app: FastAPI, resolved: Settings) -> None:
    lifecycle_reader = SnapshotIndustryLifecycle(resolved.data_dir)
    realtime_store = RealtimeProjectionStore(resolved.data_dir)

    @app.get(
        "/api/market/industry-lifecycle",
        response_model=IndustryLifecycleProjection,
        responses={404: {"description": "尚无正式数据快照"}},
    )
    def industry_lifecycle() -> IndustryLifecycleProjection:
        try:
            return lifecycle_reader.current()
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "industry_lifecycle_snapshot_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "industry_lifecycle_projection_unavailable"},
            ) from error

    @app.get(
        "/api/market/industry-lifecycle/intraday",
        response_model=IndustryLifecycleIntradayProjection,
    )
    def industry_lifecycle_intraday() -> IndustryLifecycleIntradayProjection:
        try:
            realtime = realtime_store.current_instruments()
            prices = {
                quote.instrument_id: quote.last_price
                for quote in realtime.quotes
                if quote.instrument_type == "stock" and quote.last_price is not None
            }
            return lifecycle_reader.intraday(
                prices=prices,
                market_date=realtime.market_date,
                session_id=realtime.session_id,
                state=realtime.state,
                as_of=realtime.as_of,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404,
                detail={"code": "industry_lifecycle_intraday_not_available"},
            ) from error
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "industry_lifecycle_intraday_unavailable"},
            ) from error


def _register_system_routes(app: FastAPI, resolved: Settings) -> None:
    operations = DailyOperationsReader(
        control_database=resolved.control_db_path,
        local_ops_database=resolved.local_ops_db_path,
        data_root=resolved.data_dir,
    )

    @app.get(
        "/api/system/daily-operations",
        response_model=DailyOperationsProjection,
        responses={503: {"description": "日常运行投影不可用"}},
    )
    def daily_operations() -> DailyOperationsProjection:
        try:
            return operations.current()
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "daily_operations_projection_unavailable"},
            ) from error

    @app.post(
        "/api/system/daily-run-requests",
        response_model=DailyRunRequest,
        responses={403: {"description": "只允许本地界面登记"}},
    )
    def daily_run_request(
        request: DailyRunRequestInput,
        origin: str | None = Header(default=None),
        local_action: str | None = Header(default=None, alias="X-AstraMind-Local-Action"),
    ) -> DailyRunRequest:
        allowed_origins = {
            f"http://127.0.0.1:{resolved.web_port}",
            f"http://localhost:{resolved.web_port}",
        }
        if origin not in allowed_origins or local_action != "daily-ops-v1":
            raise HTTPException(status_code=403, detail={"code": "local_action_required"})
        try:
            return DailySchedulerStore(resolved.local_ops_db_path).register_request(
                action=request.action,
                target_date=request.target_date,
                run_id=request.run_id,
                created_at=datetime.now(ZoneInfo("Asia/Shanghai")),
            )
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "daily_run_request_unavailable"},
            ) from error

    @app.get(
        "/api/system/daily-pipeline",
        response_model=DailyPipelineStatus,
        responses={404: {"description": "尚无日度数据运行状态"}},
    )
    def daily_pipeline() -> DailyPipelineStatus:
        try:
            value = DailyPipelineStore(resolved.control_db_path, resolved.data_dir).latest_status()
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "daily_pipeline_status_unavailable"},
            ) from error
        if value is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "daily_pipeline_not_started"},
            )
        return value

    @app.get(
        "/api/system/daily-decision",
        response_model=DailyDecisionStatus,
        responses={404: {"description": "尚无日度决策链状态"}},
    )
    def daily_decision() -> DailyDecisionStatus:
        try:
            value = DailyDecisionStore(
                resolved.local_ops_db_path,
                Path("var/research/daily-decision"),
            ).latest_status()
        except (ValueError, OSError, sqlite3.Error) as error:
            raise HTTPException(
                status_code=503,
                detail={"code": "daily_decision_status_unavailable"},
            ) from error
        if value is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "daily_decision_not_started"},
            )
        return value


__all__ = ["HealthResponse", "create_app"]
