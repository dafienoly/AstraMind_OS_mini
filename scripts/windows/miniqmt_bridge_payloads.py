"""Serialization helpers for the read-only MiniQMT data bridge."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from math import isfinite


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and isfinite(float(value))


def _number(value: object) -> float:
    if not isinstance(value, (int, float)):
        raise TypeError(f"expected numeric value, got {type(value).__name__}")
    return float(value)


def mapping(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {}


def market_rows(payload: object) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for instrument, table in mapping(payload).items():
        to_dict = getattr(table, "to_dict", None)
        records = to_dict("records") if callable(to_dict) else table
        if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
            rows.extend(
                {"instrument_id": instrument, **mapping(record)}
                for record in records
                if isinstance(record, Mapping)
            )
    return rows


def market_matrix_rows(payload: object) -> list[dict[str, object]]:
    rows: dict[tuple[str, object], dict[str, object]] = {}
    for field, table in mapping(payload).items():
        to_dict = getattr(table, "to_dict", None)
        columns = to_dict() if callable(to_dict) else {}
        if not isinstance(columns, Mapping):
            continue
        for market_time, instruments in columns.items():
            if not isinstance(instruments, Mapping):
                continue
            for instrument, value in instruments.items():
                instrument_id = str(instrument)
                key = (instrument_id, market_time)
                rows.setdefault(
                    key,
                    {"instrument_id": instrument_id, "time": market_time},
                )[field] = value
    usable = [
        row
        for row in rows.values()
        if any(_is_finite_number(row.get(field)) for field in ("open", "high", "low", "close"))
    ]
    by_instrument: dict[str, list[dict[str, object]]] = {}
    for row in usable:
        by_instrument.setdefault(str(row["instrument_id"]), []).append(row)
    for instrument_rows in by_instrument.values():
        instrument_rows.sort(key=lambda row: _number(row.get("time")))
        previous_close: float | None = None
        for row in instrument_rows:
            close = row.get("close")
            native_previous = row.get("preClose")
            reference_close = (
                float(native_previous)
                if isinstance(native_previous, int | float)
                and isfinite(float(native_previous))
                and float(native_previous) > 0
                else previous_close
            )
            if reference_close is not None:
                row["previous_close"] = reference_close
                if isinstance(close, int | float) and reference_close:
                    change = float(close) - reference_close
                    row["change"] = change
                    row["percent_change"] = change / reference_close * 100
            if isinstance(close, int | float) and isfinite(float(close)):
                previous_close = float(close)
    return usable


def financial_rows(payload: object, table: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for instrument, tables in mapping(payload).items():
        value = mapping(tables).get(table)
        to_dict = getattr(value, "to_dict", None)
        records = to_dict("records") if callable(to_dict) else value
        if isinstance(records, Sequence) and not isinstance(records, (str, bytes)):
            rows.extend(
                {"instrument_id": instrument, "statement_type": table, **mapping(record)}
                for record in records
                if isinstance(record, Mapping)
            )
    return rows


def nested_rows(payload: object, key_name: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, values in mapping(payload).items():
        if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
            continue
        rows.extend({key_name: key, **mapping(row)} for row in values if isinstance(row, Mapping))
    return rows


def json_safe(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return json_safe(to_dict())
    item = getattr(value, "item", None)
    if callable(item):
        return json_safe(item())
    return repr(value)


def strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


__all__ = [
    "financial_rows",
    "json_safe",
    "mapping",
    "market_matrix_rows",
    "market_rows",
    "nested_rows",
    "strings",
]
