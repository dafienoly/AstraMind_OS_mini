"""Construct a read-only realtime session after same-day 1m warm start."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from astramind_mini.config import Settings

from ..application.identity import content_hash
from ..application.realtime_projection import RealtimeQuoteProjector
from ..application.realtime_reference import load_realtime_instrument_reference
from ..application.realtime_warm_start import normalize_warm_start_minutes
from ..contracts.source import CanonicalDatasetRequest
from ..etf_foundation.registry import ETF_CODES
from ..etf_model_evidence.spread import (
    EtfSpreadMinuteProjector,
    EtfSpreadMinuteStore,
)
from .miniqmt_bridge import MiniQMTBridgeClient
from .miniqmt_source import MiniQMTSourceAdapter
from .realtime_projection_store import RealtimeProjectionStore
from .streaming_realtime_store import StreamingRealtimeStore


@dataclass(frozen=True, slots=True)
class RealtimeSessionComponents:
    bridge: MiniQMTBridgeClient
    session_id: str
    started_at: datetime
    raw_store: StreamingRealtimeStore
    projection_store: RealtimeProjectionStore
    projector: RealtimeQuoteProjector
    spread_store: EtfSpreadMinuteStore
    spread_projector: EtfSpreadMinuteProjector


async def start_realtime_session(
    settings: Settings,
    market_date: date,
    *,
    root: Path,
) -> RealtimeSessionComponents:
    xtquant_path = settings.miniqmt_xtquant_path
    quote_port = settings.miniqmt_quote_port
    if xtquant_path is None or quote_port is None:
        raise ValueError("必须固定 MiniQMT XtQuant 路径和只读行情端口")
    bridge = MiniQMTBridgeClient(
        runner=root / "scripts/windows/miniqmt_data_bridge.py",
        xtquant_path=xtquant_path,
        quote_port=quote_port,
        python_command=settings.miniqmt_python or "py",
    )
    await bridge.start()
    started_at = datetime.now().astimezone()
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
    reference = load_realtime_instrument_reference(settings.data_dir, as_of=market_date)
    projection_store = RealtimeProjectionStore(settings.data_dir)
    await _warm_start(
        bridge,
        projection_store,
        tuple(sorted(reference.universe)),
        market_date,
    )
    return RealtimeSessionComponents(
        bridge=bridge,
        session_id=session_id,
        started_at=started_at,
        raw_store=StreamingRealtimeStore(settings.data_dir),
        projection_store=projection_store,
        projector=RealtimeQuoteProjector(
            session_id=session_id,
            industry_membership=reference.industries,
            breadth_universe=reference.universe,
            instrument_names=reference.names,
            instrument_types=reference.instrument_types,
            price_limits=reference.price_limits,
        ),
        spread_store=EtfSpreadMinuteStore(settings.data_dir),
        spread_projector=EtfSpreadMinuteProjector(
            feed_session_id=session_id,
            market_date=market_date,
            universe=ETF_CODES,
        ),
    )


async def _warm_start(
    bridge: MiniQMTBridgeClient,
    store: RealtimeProjectionStore,
    universe: tuple[str, ...],
    market_date: date,
) -> None:
    now = datetime.now().astimezone()
    batch = await MiniQMTSourceAdapter(bridge).fetch(
        CanonicalDatasetRequest(
            dataset_name="minute_market",
            as_of=now,
            start_date=market_date,
            end_date=market_date,
            universe=universe,
            frequency="1m",
            allow_empty=True,
        )
    )
    rows = normalize_warm_start_minutes(
        batch,
        completed_before=now.replace(second=0, microsecond=0),
    )
    store.persist_warm_start(
        market_date=market_date,
        request_identity=batch.request_identity,
        raw_payload=batch.raw_payload,
        rows=rows,
    )


__all__ = ["RealtimeSessionComponents", "start_realtime_session"]
