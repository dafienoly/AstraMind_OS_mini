"""Inputs produced by an exact-snapshot full-universe signal scan."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .backtest_models import CandidateSignal


@dataclass(frozen=True, slots=True)
class ReplayCandidate:
    signal: CandidateSignal
    entry_date: date
    entry_open: float | None
    entry_amount_cny: float | None
    entry_buy_state: str | None
    target_exit_date: date | None
    exit_date: date | None
    exit_open: float | None


@dataclass(frozen=True, slots=True)
class ReplayPrice:
    instrument_id: str
    trade_date: date
    close: float


@dataclass(frozen=True, slots=True)
class CurrentSignalCandidate:
    signal: CandidateSignal
    reference_price: float


__all__ = ["CurrentSignalCandidate", "ReplayCandidate", "ReplayPrice"]
