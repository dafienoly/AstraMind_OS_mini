"""Run the persistent, read-only MiniQMT L1 ingestion service."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from pathlib import Path
from time import monotonic

from astramind_mini.config import Settings
from astramind_mini.data.adapters import (
    MiniQMTBridgeClient,
    MiniQMTBridgeError,
    RealtimeProjectionStore,
    StreamingRealtimeStore,
)
from astramind_mini.data.adapters.miniqmt_l1 import normalize_l1_messages
from astramind_mini.data.adapters.realtime_session import start_realtime_session
from astramind_mini.data.application.realtime_projection import RealtimeQuoteProjector
from astramind_mini.data.application.realtime_recovery import (
    recover_current_realtime_projection,
)
from astramind_mini.data.contracts import (
    FeedSessionReport,
    FeedSessionState,
    RealtimeQuoteObservation,
)
from astramind_mini.data.etf_model_evidence.spread import (
    EtfSpreadMinuteProjector,
    EtfSpreadMinuteStore,
)
from astramind_mini.local_ops.realtime_market_storage import (
    append_minute_rows,
    prune_retained_payloads,
    publish_projections,
    publish_starting_status,
)
from astramind_mini.local_ops.realtime_service_runtime import (
    SHANGHAI,
    RealtimeServiceLock,
    RealtimeStatusStore,
    active_capture_deadline,
    realtime_session_state,
)
from astramind_mini.local_ops.trading_calendar import current_open_dates

ROOT = Path(__file__).resolve().parents[1]
CONTROL_ROOT = ROOT / "var/control/realtime-market-service"


@dataclass(frozen=True, slots=True)
class SessionOutcome:
    session_id: str
    session_path: Path
    messages: int
    microbatches: int
    disconnected: bool
    failure_code: str | None = None
    failure_detail: str | None = None


async def _run_session(
    settings: Settings,
    *,
    duration_seconds: float,
    market_date: date,
    status: RealtimeStatusStore,
) -> SessionOutcome:
    components = await start_realtime_session(settings, market_date, root=ROOT)
    bridge = components.bridge
    session_id = components.session_id
    started_at = components.started_at
    projector = components.projector
    raw_messages: list[object] = []
    observations: list[RealtimeQuoteObservation] = []
    minute_paths: list[Path] = []
    sequence = messages = duplicates = 0
    batch_started = started_at
    deadline = monotonic() + duration_seconds
    last_heartbeat = monotonic()
    last_message_at: datetime | None = None
    last_microbatch_at: datetime | None = None
    disconnected = False
    disconnect_code = None
    disconnect_detail = None
    status.publish_connecting(market_date, session_id)
    try:
        await bridge.request("subscribe", markets=("SH", "SZ", "BJ"))
        status.publish(
            realtime_session_state(datetime.now(SHANGHAI)),
            market_date=market_date,
            session_id=session_id,
            feed_state="connected",
            projection_state="forming",
        )
        while monotonic() < deadline:
            event = await bridge.next_quote_event(timeout_seconds=1)
            now = datetime.now(UTC)
            if event is None:
                publish_projections(components.projection_store, projector, now)
                components.spread_store.append(components.spread_projector.drain_closed(now))
                if monotonic() - last_heartbeat >= 5:
                    await bridge.request("health", timeout_seconds=2)
                    status.publish(
                        realtime_session_state(datetime.now(SHANGHAI)),
                        market_date=market_date,
                        session_id=session_id,
                        messages=messages,
                        microbatches=sequence,
                        feed_state="connected",
                        projection_state="forming",
                        last_message_at=last_message_at,
                        last_microbatch_at=last_microbatch_at,
                    )
                    last_heartbeat = monotonic()
                continue
            received_at = datetime.fromisoformat(str(event["received_at"]))
            last_message_at = received_at
            payload = event.get("payload")
            rows, duplicate_count = normalize_l1_messages([payload], received_at)
            projector.ingest(rows)
            components.spread_projector.ingest(rows)
            raw_messages.append({"received_at": event["received_at"], "payload": payload})
            observations.extend(rows)
            messages += 1
            duplicates += duplicate_count
            if (received_at - batch_started).total_seconds() >= 1:
                components.raw_store.append(
                    session_id=session_id,
                    sequence=sequence,
                    started_at=batch_started,
                    ended_at=received_at,
                    raw_messages=raw_messages,
                    observations=tuple(observations),
                )
                publish_projections(components.projection_store, projector, received_at)
                minute_paths.extend(
                    append_minute_rows(
                        components.projection_store,
                        projector.drain_closed_minutes(),
                    )
                )
                components.spread_store.append(
                    components.spread_projector.drain_closed(received_at)
                )
                sequence += 1
                last_microbatch_at = received_at
                batch_started = received_at
                raw_messages, observations = [], []
    except MiniQMTBridgeError as error:
        disconnected = True
        disconnect_code = error.code
        disconnect_detail = error.detail or "\n".join(bridge.stderr_tail) or None
    return await _finalize_session(
        settings=settings,
        bridge=bridge,
        session_id=session_id,
        market_date=market_date,
        started_at=started_at,
        batch_started=batch_started,
        raw_messages=raw_messages,
        observations=observations,
        raw_store=components.raw_store,
        projection_store=components.projection_store,
        projector=projector,
        spread_projector=components.spread_projector,
        spread_store=components.spread_store,
        minute_paths=minute_paths,
        sequence=sequence,
        messages=messages,
        duplicates=duplicates,
        disconnected=disconnected,
        disconnect_code=disconnect_code,
        disconnect_detail=disconnect_detail,
        last_message_at=last_message_at,
        last_microbatch_at=last_microbatch_at,
        status=status,
    )


async def _finalize_session(
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
    ended_at = datetime.now(UTC)
    status.publish(
        "sealing",
        market_date=market_date,
        session_id=session_id,
        messages=messages,
        microbatches=sequence,
        feed_state="disconnected" if disconnected else "connected",
        projection_state="forming",
        last_message_at=last_message_at,
        last_microbatch_at=last_microbatch_at,
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
    projection_store.publish_current(
        projector.project(ended_at).model_copy(
            update={"state": "disconnected" if disconnected else "stale", "as_of": ended_at}
        )
    )
    projection_store.publish_instruments(
        projector.instrument_projection(ended_at).model_copy(
            update={"state": "disconnected" if disconnected else "stale", "as_of": ended_at}
        )
    )
    if not disconnected:
        completed_minutes = projector.close_completed_minutes(ended_at)
        minute_paths.extend(append_minute_rows(projection_store, completed_minutes))
    spread_store.append(spread_projector.close_open(ended_at))
    with contextlib.suppress(MiniQMTBridgeError, TimeoutError):
        await bridge.stop()
    report = FeedSessionReport(
        session_id=session_id,
        provider="miniqmt",
        client_version=bridge.provider_version,
        state=(
            FeedSessionState.DISCONNECTED
            if disconnected
            else (FeedSessionState.COMPLETE if messages else FeedSessionState.EMPTY)
        ),
        markets=("SH", "SZ", "BJ"),
        market_date=market_date,
        subscribed_at=started_at,
        ended_at=ended_at,
        microbatch_ids=(),
        received_messages=messages,
        duplicate_messages=duplicates,
        disconnects=int(disconnected),
        known_gaps=(
            (f"bridge_disconnected:{disconnect_code}",)
            if disconnected
            else (() if messages else ("session_without_messages",))
        ),
    )
    session_path = raw_store.finalize(report)
    if minute_paths:
        projection_store.verify_session_aggregation(
            session_id=session_id,
            aggregate_paths=minute_paths,
        )
    prune_retained_payloads(settings, projection_store, market_date)
    status.publish(
        "blocked" if disconnected else "reconciled",
        market_date=market_date,
        session_id=session_id,
        messages=messages,
        microbatches=sequence,
        feed_state="disconnected" if disconnected else "reconciled",
        projection_state="blocked" if disconnected else "sealed",
        last_message_at=last_message_at,
        last_microbatch_at=last_microbatch_at,
        last_error=disconnect_code,
        recovery_action=(
            "检查 MiniQMT 只读行情端口与 bridge stderr 后重试" if disconnected else None
        ),
    )
    return SessionOutcome(
        session_id=session_id,
        session_path=session_path,
        messages=messages,
        microbatches=sequence,
        disconnected=disconnected,
        failure_code=disconnect_code,
        failure_detail=disconnect_detail,
    )


async def _run_with_retries(
    settings: Settings,
    *,
    duration_seconds: float,
    market_date: date,
    status: RealtimeStatusStore,
) -> tuple[SessionOutcome, ...]:
    deadline = monotonic() + duration_seconds
    outcomes = []
    failures: list[dict[str, object]] = []
    last_error: MiniQMTBridgeError | None = None
    for attempt in range(4):
        remaining = max(0.0, deadline - monotonic())
        if remaining == 0:
            break
        try:
            outcome = await _run_session(
                settings,
                duration_seconds=remaining,
                market_date=market_date,
                status=status,
            )
        except MiniQMTBridgeError as error:
            last_error = error
            failures.append(
                {
                    "attempt": attempt + 1,
                    "error_type": type(error).__name__,
                    "error_code": error.code,
                    "detail": error.detail,
                    "failed_at": datetime.now(UTC).isoformat(),
                }
            )
            status.publish(
                "recovering",
                market_date=market_date,
                feed_state="retrying",
                projection_state="blocked",
                last_error=error.code,
                retry_failures=tuple(failures),
                recovery_action="检查最后一次具体 bridge 错误后重试",
            )
            if attempt == 3:
                raise
        else:
            outcomes.append(outcome)
            if not outcome.disconnected:
                break
            failures.append(
                {
                    "attempt": attempt + 1,
                    "error_type": "MiniQMTBridgeError",
                    "error_code": outcome.failure_code or "bridge_disconnected",
                    "detail": outcome.failure_detail,
                    "failed_at": datetime.now(UTC).isoformat(),
                }
            )
            status.publish(
                "recovering",
                market_date=market_date,
                feed_state="retrying",
                projection_state="blocked",
                last_error=outcome.failure_code or "bridge_disconnected",
                retry_failures=tuple(failures),
                recovery_action="检查 bridge stderr 与只读行情端口后重连",
            )
            if attempt == 3:
                raise MiniQMTBridgeError(
                    outcome.failure_code or "bridge_disconnected",
                    outcome.failure_detail or "reconnect_limit_exhausted",
                )
        await asyncio.sleep(min(2**attempt, 8))
    if not outcomes and last_error is not None:
        raise last_error
    return tuple(outcomes)


async def _run_continuously(
    settings: Settings,
    status: RealtimeStatusStore,
) -> None:
    last_maintenance: date | None = None
    while True:
        now = datetime.now(UTC)
        open_dates = current_open_dates(settings.data_dir)
        active = active_capture_deadline(now, open_dates)
        today = now.astimezone(SHANGHAI).date()
        if active is None:
            local_time = now.astimezone(SHANGHAI).time().replace(tzinfo=None)
            state = "preopen" if time(8, 55) <= local_time < time(9, 30) else "waiting"
            status.publish(
                state,
                market_date=today,
                feed_state="not_started",
                projection_state="unknown",
            )
            if last_maintenance != today:
                prune_retained_payloads(
                    settings,
                    RealtimeProjectionStore(settings.data_dir),
                    today,
                )
                last_maintenance = today
            await asyncio.sleep(30)
            continue
        market_date, deadline = active
        duration = max(1.0, (deadline - now.astimezone(SHANGHAI)).total_seconds())
        await _run_with_retries(
            settings,
            duration_seconds=duration,
            market_date=market_date,
            status=status,
        )


async def run(duration_seconds: float | None) -> int:
    settings = Settings()
    if settings.miniqmt_xtquant_path is None or settings.miniqmt_quote_port is None:
        raise ValueError("必须固定 MiniQMT XtQuant 路径和只读行情端口")
    status = RealtimeStatusStore(CONTROL_ROOT)
    today = datetime.now(SHANGHAI).date()
    publish_starting_status(settings, status, today)
    with contextlib.suppress(FileNotFoundError, ValueError, OSError):
        recover_current_realtime_projection(settings.data_dir)
    if duration_seconds is None:
        await _run_continuously(settings, status)
        return 0
    market_date = datetime.now(SHANGHAI).date()
    outcomes = await _run_with_retries(
        settings,
        duration_seconds=duration_seconds,
        market_date=market_date,
        status=status,
    )
    if not outcomes:
        raise RuntimeError("capture_deadline_elapsed_before_session")
    print(f"sessions={len(outcomes)}")
    print(f"session_id={outcomes[-1].session_id}")
    print(f"messages={sum(item.messages for item in outcomes)}")
    print(f"microbatches={sum(item.microbatches for item in outcomes)}")
    print(f"session={outcomes[-1].session_path}")
    print("broker_actions_allowed=false")
    status.publish(
        "stopped",
        market_date=market_date,
        session_id=outcomes[-1].session_id,
        messages=sum(item.messages for item in outcomes),
        microbatches=sum(item.microbatches for item in outcomes),
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--duration-seconds",
        type=float,
        help="省略时按交易日持续运行；真实负载验收使用 900 秒",
    )
    args = parser.parse_args()
    if args.duration_seconds is not None and args.duration_seconds < 5:
        parser.error("--duration-seconds 必须不少于 5 秒")
    status = RealtimeStatusStore(CONTROL_ROOT)
    try:
        with RealtimeServiceLock(CONTROL_ROOT):
            return asyncio.run(run(args.duration_seconds))
    except RuntimeError as error:
        if str(error) == "realtime_market_service_already_running":
            print("state=already_running")
            print("broker_actions_allowed=false")
            return 0
        existing = status.read()
        status.publish(
            "blocked",
            process_state="exited",
            feed_state="blocked",
            projection_state="blocked",
            exit_code=1,
            last_error=(existing.last_error if existing and existing.last_error else str(error)),
            retry_failures=existing.retry_failures if existing else (),
            recovery_action="读取 service.log 与 retry_failures，修复具体根因后再启动",
            successful_heartbeat=False,
        )
        raise
    except KeyboardInterrupt:
        status.publish("stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
