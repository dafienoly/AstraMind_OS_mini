"""Run the persistent, read-only MiniQMT L1 ingestion service."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, date, datetime
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
from astramind_mini.data.application.identity import content_hash
from astramind_mini.data.application.realtime_projection import RealtimeQuoteProjector
from astramind_mini.data.application.realtime_recovery import (
    recover_current_realtime_projection,
)
from astramind_mini.data.application.realtime_reference import (
    load_realtime_instrument_reference,
)
from astramind_mini.data.contracts import (
    FeedSessionReport,
    FeedSessionState,
    RealtimeMinuteBar,
    RealtimeQuoteObservation,
)
from astramind_mini.data.etf_foundation.registry import ETF_CODES
from astramind_mini.data.etf_model_evidence.spread import (
    EtfSpreadMinuteProjector,
    EtfSpreadMinuteStore,
)
from astramind_mini.local_ops.realtime_service_runtime import (
    SHANGHAI,
    RealtimeServiceLock,
    RealtimeStatusStore,
    active_capture_deadline,
    retained_open_dates,
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


@dataclass(frozen=True, slots=True)
class SessionComponents:
    bridge: MiniQMTBridgeClient
    session_id: str
    started_at: datetime
    raw_store: StreamingRealtimeStore
    projection_store: RealtimeProjectionStore
    projector: RealtimeQuoteProjector
    spread_store: EtfSpreadMinuteStore
    spread_projector: EtfSpreadMinuteProjector


async def _start_session(
    settings: Settings,
    market_date: date,
) -> SessionComponents:
    xtquant_path = settings.miniqmt_xtquant_path
    quote_port = settings.miniqmt_quote_port
    if xtquant_path is None or quote_port is None:
        raise ValueError("必须固定 MiniQMT XtQuant 路径和只读行情端口")
    bridge = MiniQMTBridgeClient(
        runner=ROOT / "scripts/windows/miniqmt_data_bridge.py",
        xtquant_path=xtquant_path,
        quote_port=quote_port,
        python_command=settings.miniqmt_python or "py",
    )
    await bridge.start()
    started_at = datetime.now(UTC)
    session_id = content_hash(
        {
            "provider": "miniqmt",
            "provider_version": bridge.provider_version,
            "client_fingerprint": bridge.client_fingerprint,
            "started_at": started_at,
            "market_date": market_date,
            "quote_port": quote_port,
        }
    )
    reference = load_realtime_instrument_reference(
        settings.data_dir,
        as_of=market_date,
    )
    projector = RealtimeQuoteProjector(
        session_id=session_id,
        industry_membership=reference.industries,
        breadth_universe=reference.universe,
        instrument_names=reference.names,
        instrument_types=reference.instrument_types,
        price_limits=reference.price_limits,
    )
    return SessionComponents(
        bridge=bridge,
        session_id=session_id,
        started_at=started_at,
        raw_store=StreamingRealtimeStore(settings.data_dir),
        projection_store=RealtimeProjectionStore(settings.data_dir),
        projector=projector,
        spread_store=EtfSpreadMinuteStore(settings.data_dir),
        spread_projector=EtfSpreadMinuteProjector(
            feed_session_id=session_id,
            market_date=market_date,
            universe=ETF_CODES,
        ),
    )


async def _run_session(
    settings: Settings,
    *,
    duration_seconds: float,
    market_date: date,
    status: RealtimeStatusStore,
) -> SessionOutcome:
    components = await _start_session(settings, market_date)
    bridge = components.bridge
    session_id = components.session_id
    started_at = components.started_at
    raw_store = components.raw_store
    projection_store = components.projection_store
    projector = components.projector
    spread_store = components.spread_store
    spread_projector = components.spread_projector
    raw_messages: list[object] = []
    observations: list[RealtimeQuoteObservation] = []
    minute_paths: list[Path] = []
    sequence = messages = duplicates = 0
    batch_started = started_at
    deadline = monotonic() + duration_seconds
    last_heartbeat = monotonic()
    disconnected = False
    disconnect_code = None
    status.publish("connecting", market_date=market_date, session_id=session_id)
    try:
        await bridge.request("subscribe", markets=("SH", "SZ", "BJ"))
        status.publish("capturing", market_date=market_date, session_id=session_id)
        while monotonic() < deadline:
            event = await bridge.next_quote_event(timeout_seconds=1)
            now = datetime.now(UTC)
            if event is None:
                _publish_projections(projection_store, projector, now)
                spread_store.append(spread_projector.drain_closed(now))
                if monotonic() - last_heartbeat >= 5:
                    await bridge.request("health", timeout_seconds=2)
                    status.publish(
                        "capturing",
                        market_date=market_date,
                        session_id=session_id,
                        messages=messages,
                        microbatches=sequence,
                    )
                    last_heartbeat = monotonic()
                continue
            received_at = datetime.fromisoformat(str(event["received_at"]))
            payload = event.get("payload")
            rows, duplicate_count = normalize_l1_messages([payload], received_at)
            projector.ingest(rows)
            spread_projector.ingest(rows)
            raw_messages.append({"received_at": event["received_at"], "payload": payload})
            observations.extend(rows)
            messages += 1
            duplicates += duplicate_count
            if (received_at - batch_started).total_seconds() >= 1:
                raw_store.append(
                    session_id=session_id,
                    sequence=sequence,
                    started_at=batch_started,
                    ended_at=received_at,
                    raw_messages=raw_messages,
                    observations=tuple(observations),
                )
                _publish_projections(projection_store, projector, received_at)
                minute_paths.extend(
                    _append_minute_rows(
                        projection_store,
                        projector.drain_closed_minutes(),
                    )
                )
                spread_store.append(spread_projector.drain_closed(received_at))
                sequence += 1
                batch_started = received_at
                raw_messages, observations = [], []
    except MiniQMTBridgeError as error:
        disconnected = True
        disconnect_code = error.code
    return await _finalize_session(
        settings=settings,
        bridge=bridge,
        session_id=session_id,
        market_date=market_date,
        started_at=started_at,
        batch_started=batch_started,
        raw_messages=raw_messages,
        observations=observations,
        raw_store=raw_store,
        projection_store=projection_store,
        projector=projector,
        spread_projector=spread_projector,
        spread_store=spread_store,
        minute_paths=minute_paths,
        sequence=sequence,
        messages=messages,
        duplicates=duplicates,
        disconnected=disconnected,
        disconnect_code=disconnect_code,
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
    status: RealtimeStatusStore,
) -> SessionOutcome:
    ended_at = datetime.now(UTC)
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
    minute_paths.extend(_append_minute_rows(projection_store, projector.close_open_minutes()))
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
    _prune_retained_payloads(settings, projection_store, market_date)
    status.publish(
        "disconnected" if disconnected else "waiting",
        market_date=market_date,
        session_id=session_id,
        messages=messages,
        microbatches=sequence,
        last_error=disconnect_code,
    )
    return SessionOutcome(
        session_id=session_id,
        session_path=session_path,
        messages=messages,
        microbatches=sequence,
        disconnected=disconnected,
    )


def _append_minute_rows(
    store: RealtimeProjectionStore,
    rows: tuple[RealtimeMinuteBar, ...],
) -> tuple[Path, ...]:
    grouped: dict[date, list[RealtimeMinuteBar]] = {}
    for row in rows:
        grouped.setdefault(row.minute.astimezone(SHANGHAI).date(), []).append(row)
    paths = []
    for market_date, dated_rows in sorted(grouped.items()):
        path = store.append_aggregate(
            kind="1m",
            market_date=market_date,
            rows=dated_rows,
        )
        if path is not None:
            paths.append(path)
    return tuple(paths)


def _publish_projections(
    store: RealtimeProjectionStore,
    projector: RealtimeQuoteProjector,
    now: datetime,
) -> None:
    store.publish_current(projector.project(now))
    store.publish_instruments(projector.instrument_projection(now))


def _prune_retained_payloads(
    settings: Settings,
    store: RealtimeProjectionStore,
    today: date,
) -> None:
    with contextlib.suppress(FileNotFoundError, ValueError):
        open_dates = current_open_dates(settings.data_dir)
        store.prune_raw_payloads(retained_dates=retained_open_dates(open_dates, today))


async def _run_with_retries(
    settings: Settings,
    *,
    duration_seconds: float,
    market_date: date,
    status: RealtimeStatusStore,
) -> tuple[SessionOutcome, ...]:
    deadline = monotonic() + duration_seconds
    outcomes = []
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
            status.publish("recovering", market_date=market_date, last_error=error.code)
            if attempt == 3:
                raise
        else:
            outcomes.append(outcome)
            if not outcome.disconnected:
                break
            if attempt == 3:
                raise MiniQMTBridgeError("reconnect_limit_exhausted")
        await asyncio.sleep(min(2**attempt, 8))
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
            status.publish("waiting", market_date=today)
            if last_maintenance != today:
                _prune_retained_payloads(
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
        raise RuntimeError("没有创建行情会话")
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
        status.publish("error", last_error=str(error))
        raise
    except KeyboardInterrupt:
        status.publish("stopped")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
