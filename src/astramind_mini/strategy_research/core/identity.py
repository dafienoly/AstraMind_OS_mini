"""Deterministic content identity for one weekly core input."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from astramind_mini.contracts import DataSnapshot

from ..application.identity import research_hash
from .contracts import CoreDatasetSlice, CoreInputLayer, CoreInputSnapshot

_FORBIDDEN_LAYERS = {
    CoreInputLayer.CURRENT_SESSION,
    CoreInputLayer.FORMING_MINUTE,
    CoreInputLayer.UNSEALED_TICK,
}


def freeze_core_input_snapshot(
    *,
    data_snapshot: DataSnapshot,
    decision_date: date,
    cutoff_at: datetime,
    common_calendar_id: str,
    common_calendar_hash: str,
    universe_content_hash: str,
    datasets: Sequence[CoreDatasetSlice],
) -> CoreInputSnapshot:
    """Validate immutable inputs and derive an order-independent content identity."""
    if data_snapshot.as_of > cutoff_at:
        raise ValueError("a future DataSnapshot cannot be bound to an earlier core cutoff")
    ordered = tuple(sorted(datasets, key=lambda item: item.dataset_name))
    names = [item.dataset_name for item in ordered]
    if len(names) != len(set(names)):
        raise ValueError("core dataset slices must have unique names")

    snapshot_refs = {item.dataset_name: item for item in data_snapshot.datasets}
    for item in ordered:
        reference = snapshot_refs.get(item.dataset_name)
        if reference is None:
            raise ValueError(f"dataset is not part of DataSnapshot: {item.dataset_name}")
        if (
            reference.dataset_version != item.dataset_version
            or reference.schema_version != item.schema_version
            or reference.content_hash != item.content_hash
        ):
            raise ValueError(f"dataset slice does not match DataSnapshot: {item.dataset_name}")
        if item.max_available_at > cutoff_at or item.max_market_date > decision_date:
            raise ValueError(f"dataset slice crosses the core cutoff: {item.dataset_name}")
        if item.input_layer in _FORBIDDEN_LAYERS:
            raise ValueError(f"mutable or unsealed input layer is forbidden: {item.input_layer}")
        if not item.sealed:
            raise ValueError(f"core input dataset must be immutable: {item.dataset_name}")

    payload = {
        "data_snapshot": data_snapshot,
        "decision_date": decision_date,
        "cutoff_at": cutoff_at,
        "common_calendar_id": common_calendar_id,
        "common_calendar_hash": common_calendar_hash,
        "data_semantics_version": "core-data-semantics-v1",
        "universe_version": "U0-v1",
        "universe_content_hash": universe_content_hash,
        "datasets": ordered,
    }
    content_hash = research_hash(payload)
    return CoreInputSnapshot(
        core_input_snapshot_id=f"core-input:{content_hash.removeprefix('sha256:')}",
        content_hash=content_hash,
        data_snapshot=data_snapshot,
        decision_date=decision_date,
        cutoff_at=cutoff_at,
        common_calendar_id=common_calendar_id,
        common_calendar_hash=common_calendar_hash,
        data_semantics_version="core-data-semantics-v1",
        universe_version="U0-v1",
        universe_content_hash=universe_content_hash,
        datasets=ordered,
    )


__all__ = ["freeze_core_input_snapshot"]
