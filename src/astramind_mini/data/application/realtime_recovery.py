"""Recover a stale current projection from the latest retained normalized microbatch."""

from __future__ import annotations

import gzip
import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import TypeAdapter

from ..adapters.realtime_projection_store import RealtimeProjectionStore
from ..contracts.realtime import RealtimeQuoteObservation
from .realtime_projection import RealtimeQuoteProjector
from .realtime_reference import load_realtime_instrument_reference


def recover_current_realtime_projection(data_root: Path) -> bool:
    normalized = _latest_normalized(data_root)
    if normalized is None:
        return False
    session = json.loads((normalized.parent / "session.json").read_text(encoding="utf-8"))
    session_id = str(session["session_id"])
    market_date = _market_date(session)
    reference = load_realtime_instrument_reference(data_root, as_of=market_date)
    rows = TypeAdapter(tuple[RealtimeQuoteObservation, ...]).validate_json(
        gzip.decompress(normalized.read_bytes())
    )
    if not rows:
        return False
    projector = RealtimeQuoteProjector(
        session_id=session_id,
        industry_membership=reference.industries,
        breadth_universe=reference.universe,
        instrument_names=reference.names,
        instrument_types=reference.instrument_types,
        price_limits=reference.price_limits,
    )
    projector.ingest(rows)
    now = datetime.now(UTC)
    store = RealtimeProjectionStore(data_root)
    store.publish_current(
        projector.project(now).model_copy(update={"state": "stale", "as_of": now})
    )
    store.publish_instruments(
        projector.instrument_projection(now).model_copy(update={"state": "stale", "as_of": now})
    )
    return True


def _latest_normalized(data_root: Path) -> Path | None:
    sessions = data_root / "realtime" / "miniqmt" / "sessions"
    paths = tuple(sessions.glob("*/*.normalized.json.gz"))
    return max(paths, key=lambda path: path.stat().st_mtime) if paths else None


def _market_date(session: dict[str, object]) -> date:
    value = session.get("market_date")
    if value:
        return date.fromisoformat(str(value))
    return datetime.fromisoformat(str(session["subscribed_at"])).date()


__all__ = ["recover_current_realtime_projection"]
