"""Point-in-time construction of common H20/H60 forward-return labels."""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, datetime
from typing import cast

from ...application.identity import research_hash
from ..contracts import CoreUniverseDecision
from ..universe import core_universe_content_hash
from .models import (
    CoreForwardPriceObservation,
    CoreForwardReturnLabelBatch,
    CoreForwardReturnLabelRow,
    CoreForwardReturnLabelSpec,
    CoreLabelReason,
)


def average_rank_percentiles(values: Sequence[tuple[str, float]]) -> dict[str, float]:
    """Return deterministic ascending average-rank percentiles."""
    ordered = sorted(values, key=lambda item: (item[1], item[0]))
    if len(ordered) < 2:
        return {}
    result: dict[str, float] = {}
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = ((index + 1) + end) / 2.0
        percentile = (average_rank - 1.0) / (len(ordered) - 1)
        for instrument_id, _ in ordered[index:end]:
            result[instrument_id] = percentile
        index = end
    return result


def build_core_forward_return_label_batch(
    *,
    spec: CoreForwardReturnLabelSpec,
    decision_date: date,
    common_sessions: Sequence[date],
    universe_rows: Sequence[CoreUniverseDecision],
    prices: Sequence[CoreForwardPriceObservation],
    label_data_snapshot_id: str,
    label_data_snapshot_content_hash: str,
    label_data_snapshot_as_of: datetime,
    label_available_cutoff: datetime,
) -> CoreForwardReturnLabelBatch:
    """Build one audited daily label cross-section without future backfill."""
    sessions = _validate_sessions(common_sessions, decision_date)
    universe = tuple(sorted(universe_rows, key=lambda item: item.instrument_id))
    _validate_universe(universe, decision_date)
    decision_index = sessions.index(decision_date)
    terminal_index = decision_index + spec.horizon.sessions
    entry_index = decision_index + spec.entry_offset_common_sessions
    has_dates = terminal_index < len(sessions) and entry_index < len(sessions)
    entry_date = sessions[entry_index] if has_dates else None
    terminal_date = sessions[terminal_index] if has_dates else None
    matured = bool(
        has_dates
        and terminal_date is not None
        and label_data_snapshot_as_of <= label_available_cutoff
        and label_data_snapshot_as_of.date() >= terminal_date
    )
    selected_prices = (
        _canonical_visible_prices(
            prices,
            target_dates=(entry_date, terminal_date),
            cutoff=label_data_snapshot_as_of,
        )
        if matured
        else {}
    )
    provisional = _provisional_rows(
        universe=universe,
        entry_date=entry_date,
        terminal_date=terminal_date,
        prices=selected_prices,
        matured=matured,
    )
    valid_values = tuple(
        (item.instrument_id, item.absolute_return)
        for item in provisional
        if item.research_member and item.absolute_return is not None
    )
    percentiles = average_rank_percentiles(
        tuple((instrument, float(value)) for instrument, value in valid_values)
    )
    rows = _finalize_rows(provisional, percentiles)
    universe_hash = core_universe_content_hash(universe)
    counts = (
        len(universe),
        sum(item.research_member for item in universe),
        len(valid_values),
    )
    coverage = counts[2] / counts[1] if counts[1] else 0.0
    payload = {
        "schema": "core-forward-return-label-batch-v1",
        "spec": spec,
        "decision_date": decision_date,
        "entry_date": entry_date,
        "horizon_close_date": terminal_date,
        "decision_universe_content_hash": universe_hash,
        "universe_rows": universe,
        "label_data_snapshot_id": label_data_snapshot_id,
        "label_data_snapshot_content_hash": label_data_snapshot_content_hash,
        "label_data_snapshot_as_of": label_data_snapshot_as_of,
        "label_available_cutoff": label_available_cutoff,
        "matured": matured,
        "n_universe_rows": counts[0],
        "n_research_members": counts[1],
        "n_valid_returns": counts[2],
        "label_coverage": coverage,
        "rows": rows,
    }
    return _freeze_label_batch(payload)


def _freeze_label_batch(
    payload: dict[str, object],
) -> CoreForwardReturnLabelBatch:
    content_hash = research_hash(payload)
    return CoreForwardReturnLabelBatch.model_validate(
        {
            "batch_id": f"core-label-batch:{content_hash.removeprefix('sha256:')}",
            "content_hash": content_hash,
            **{key: value for key, value in payload.items() if key != "schema"},
        }
    )


def _validate_sessions(common_sessions: Sequence[date], decision_date: date) -> tuple[date, ...]:
    sessions = tuple(common_sessions)
    if tuple(sorted(set(sessions))) != sessions:
        raise ValueError("label common sessions must be unique and ordered")
    if decision_date not in sessions:
        raise ValueError("label decision date must be a common session")
    return sessions


def _validate_universe(
    universe: tuple[CoreUniverseDecision, ...],
    decision_date: date,
) -> None:
    if not universe or len({item.instrument_id for item in universe}) != len(universe):
        raise ValueError("label universe must be non-empty and unique")
    if any(item.decision_date != decision_date for item in universe):
        raise ValueError("label universe rows must bind the decision date")


def _canonical_visible_prices(
    prices: Sequence[CoreForwardPriceObservation],
    *,
    target_dates: tuple[date | None, date | None],
    cutoff: datetime,
) -> dict[tuple[str, date], CoreForwardPriceObservation]:
    if None in target_dates:
        return {}
    grouped: dict[tuple[str, date], list[CoreForwardPriceObservation]] = defaultdict(list)
    for item in prices:
        if item.trade_date in target_dates and item.available_at <= cutoff:
            grouped[(item.instrument_id, item.trade_date)].append(item)
    selected: dict[tuple[str, date], CoreForwardPriceObservation] = {}
    for key, rows in grouped.items():
        latest = max(item.available_at for item in rows)
        authoritative = [item for item in rows if item.available_at == latest]
        payloads = {
            (item.research_open, item.research_close, item.source_record_hash)
            for item in authoritative
        }
        if len(payloads) != 1:
            raise ValueError("conflicting authoritative forward price observations")
        selected[key] = min(authoritative, key=lambda item: item.source_record_hash)
    return selected


def _provisional_rows(
    *,
    universe: tuple[CoreUniverseDecision, ...],
    entry_date: date | None,
    terminal_date: date | None,
    prices: dict[tuple[str, date], CoreForwardPriceObservation],
    matured: bool,
) -> tuple[CoreForwardReturnLabelRow, ...]:
    rows: list[CoreForwardReturnLabelRow] = []
    for decision in universe:
        if not decision.research_member:
            rows.append(
                _invalid_row(
                    decision.instrument_id,
                    False,
                    CoreLabelReason.NOT_RESEARCH_MEMBER,
                )
            )
            continue
        if not matured or entry_date is None or terminal_date is None:
            rows.append(_invalid_row(decision.instrument_id, True, CoreLabelReason.NOT_MATURED))
            continue
        entry = prices.get((decision.instrument_id, entry_date))
        terminal = prices.get((decision.instrument_id, terminal_date))
        if entry is None or not _valid_price(entry.research_open):
            rows.append(_invalid_row(decision.instrument_id, True, CoreLabelReason.ENTRY_MISSING))
            continue
        if terminal is None or not _valid_price(terminal.research_close):
            rows.append(
                _invalid_row(
                    decision.instrument_id,
                    True,
                    CoreLabelReason.HORIZON_CLOSE_MISSING,
                )
            )
            continue
        absolute_return = (
            cast(float, terminal.research_close) / cast(float, entry.research_open) - 1.0
        )
        rows.append(
            CoreForwardReturnLabelRow.model_construct(
                instrument_id=decision.instrument_id,
                research_member=True,
                absolute_return=absolute_return,
                percentile=None,
                reason_code=None,
            )
        )
    return tuple(rows)


def _finalize_rows(
    provisional: tuple[CoreForwardReturnLabelRow, ...],
    percentiles: dict[str, float],
) -> tuple[CoreForwardReturnLabelRow, ...]:
    if not percentiles:
        return tuple(
            item
            if item.absolute_return is None
            else _invalid_row(
                item.instrument_id,
                item.research_member,
                CoreLabelReason.CROSS_SECTION_INSUFFICIENT,
                absolute_return=item.absolute_return,
            )
            for item in provisional
        )
    return tuple(
        item
        if item.absolute_return is None
        else CoreForwardReturnLabelRow(
            instrument_id=item.instrument_id,
            research_member=True,
            absolute_return=item.absolute_return,
            percentile=percentiles[item.instrument_id],
        )
        for item in provisional
    )


def _invalid_row(
    instrument_id: str,
    research_member: bool,
    reason: CoreLabelReason,
    *,
    absolute_return: float | None = None,
) -> CoreForwardReturnLabelRow:
    return CoreForwardReturnLabelRow(
        instrument_id=instrument_id,
        research_member=research_member,
        absolute_return=absolute_return,
        reason_code=reason,
    )


def _valid_price(value: float | None) -> bool:
    return value is not None and math.isfinite(value) and value > 0.0


__all__ = ["average_rank_percentiles", "build_core_forward_return_label_batch"]
