"""Fail-closed finalization for one read-only realtime feed session."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    MiniQMTBridgeClient,
    MiniQMTBridgeError,
    RealtimeProjectionStore,
    StreamingRealtimeStore,
)
from astramind_mini.data.application.realtime_projection import RealtimeQuoteProjector
from astramind_mini.data.contracts import (
    FeedSessionReport,
    FeedSessionState,
    RealtimeQuoteObservation,
)
from astramind_mini.data.etf_model_evidence.spread import (
    EtfSpreadMinuteProjector,
    EtfSpreadMinuteStore,
)

from .realtime_market_storage import append_minute_rows, prune_retained_payloads
from .realtime_service_runtime import RealtimeStatusStore


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    session_id: str
    session_path: Path
    messages: int
    microbatches: int
    disconnected: bool
    reconciled: bool
    failure_code: str | None = None
    failure_detail: str | None = None


async def finalize_realtime_session(
    *,
    settings: Settings,
    bridge: MiniQMTBridgeClient,
    session_id: str,
    market_date: date,
    started_at: datetime,
    batch_started: datetime,
    raw_messages: list[object],
    observations: list[RealtimeQuoteObservation],
    raw_store: StreamingRealtimeStore,
    projection_store: RealtimeProjectionStore,
    projector: RealtimeQuoteProjector,
    spread_projector: EtfSpreadMinuteProjector,
    spread_store: EtfSpreadMinuteStore,
    minute_paths: list[Path],
    sequence: int,
    messages: int,
    duplicates: int,
    disconnected: bool,
    disconnect_code: str | None,
    disconnect_detail: str | None,
    last_message_at: datetime | None,
    last_microbatch_at: datetime | None,
    status: RealtimeStatusStore,
) -> SessionOutcome:
    ended_at = datetime.now().astimezone()
    _publish_sealing(
        status,
        market_date,
        session_id,
        messages,
        sequence,
        disconnected,
        last_message_at,
        last_microbatch_at,
    )
    if raw_messages:
        raw_store.append(
            session_id=session_id,
            sequence=sequence,
            started_at=batch_started,
            ended_at=ended_at,
            raw_messages=raw_messages,
            observations=tuple(observations),
        )
        sequence += 1
    _publish_terminal_projections(projection_store, projector, ended_at, disconnected)
    if disconnected:
        projection_store.persist_session_parts(
            market_date=market_date,
            rows=projector.snapshot_open_minutes("bridge_disconnected"),
        )
    else:
        minute_paths.extend(
            append_minute_rows(
                projection_store,
                projector.close_completed_minutes(ended_at),
            )
        )
    spread_store.append(spread_projector.close_open(ended_at))
    with contextlib.suppress(MiniQMTBridgeError, TimeoutError):
        await bridge.stop()
    report = _session_report(
        bridge,
        session_id,
        market_date,
        started_at,
        ended_at,
        messages,
        duplicates,
        disconnected,
        disconnect_code,
    )
    session_path = raw_store.finalize(report)
    verified, verification_error = _verify(projection_store, session_id, minute_paths, messages)
    prune_retained_payloads(settings, projection_store, market_date)
    _publish_result(
        status,
        market_date,
        session_id,
        messages,
        sequence,
        disconnected,
        verified,
        disconnect_code,
        verification_error,
        last_message_at,
        last_microbatch_at,
    )
    return SessionOutcome(
        session_id=session_id,
        session_path=session_path,
        messages=messages,
        microbatches=sequence,
        disconnected=disconnected,
        reconciled=verified,
        failure_code=disconnect_code,
        failure_detail=disconnect_detail,
    )


def _verify(
    store: RealtimeProjectionStore,
    session_id: str,
    paths: list[Path],
    messages: int,
) -> tuple[bool, str]:
    if not paths or not messages:
        return False, "session_without_minute_evidence"
    try:
        store.verify_session_aggregation(session_id=session_id, aggregate_paths=paths)
    except ValueError as error:
        return False, str(error)
    return True, ""


def _publish_sealing(
    status: RealtimeStatusStore,
    market_date: date,
    session_id: str,
    messages: int,
    microbatches: int,
    disconnected: bool,
    last_message_at: datetime | None,
    last_microbatch_at: datetime | None,
) -> None:
    status.publish(
        "sealing",
        market_date=market_date,
        session_id=session_id,
        messages=messages,
        microbatches=microbatches,
        feed_state="disconnected" if disconnected else "connected",
        projection_state="forming",
        last_message_at=last_message_at,
        last_microbatch_at=last_microbatch_at,
    )


def _publish_terminal_projections(
    store: RealtimeProjectionStore,
    projector: RealtimeQuoteProjector,
    ended_at: datetime,
    disconnected: bool,
) -> None:
    state = "disconnected" if disconnected else "stale"
    store.publish_current(projector.project(ended_at).model_copy(update={"state": state}))
    store.publish_instruments(
        projector.instrument_projection(ended_at).model_copy(update={"state": state})
    )


def _session_report(
    bridge: MiniQMTBridgeClient,
    session_id: str,
    market_date: date,
    started_at: datetime,
    ended_at: datetime,
    messages: int,
    duplicates: int,
    disconnected: bool,
    disconnect_code: str | None,
) -> FeedSessionReport:
    return FeedSessionReport(
        session_id=session_id,
        provider="miniqmt",
        client_version=bridge.provider_version,
        state=FeedSessionState.DISCONNECTED
        if disconnected
        else (FeedSessionState.COMPLETE if messages else FeedSessionState.EMPTY),
        markets=("SH", "SZ", "BJ"),
        market_date=market_date,
        subscribed_at=started_at,
        ended_at=ended_at,
        microbatch_ids=(),
        received_messages=messages,
        duplicate_messages=duplicates,
        disconnects=int(disconnected),
        known_gaps=(f"bridge_disconnected:{disconnect_code}",)
        if disconnected
        else (() if messages else ("session_without_messages",)),
    )


def _publish_result(
    status: RealtimeStatusStore,
    market_date: date,
    session_id: str,
    messages: int,
    microbatches: int,
    disconnected: bool,
    verified: bool,
    disconnect_code: str | None,
    verification_error: str,
    last_message_at: datetime | None,
    last_microbatch_at: datetime | None,
) -> None:
    blocked = disconnected or not verified
    status.publish(
        "blocked" if blocked else "reconciled",
        market_date=market_date,
        session_id=session_id,
        messages=messages,
        microbatches=microbatches,
        feed_state="disconnected" if disconnected else "blocked" if not verified else "reconciled",
        projection_state="blocked" if blocked else "sealed",
        last_message_at=last_message_at,
        last_microbatch_at=last_microbatch_at,
        last_error=disconnect_code
        if disconnected
        else verification_error
        if not verified
        else None,
        recovery_action=(
            "检查 MiniQMT 只读行情端口与 bridge stderr 后重试"
            if disconnected
            else "检查分钟覆盖与微批对账证据"
            if not verified
            else None
        ),
    )


__all__ = ["SessionOutcome", "finalize_realtime_session"]
