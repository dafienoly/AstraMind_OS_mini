"""Standalone synthetic panels and input mapping for Alpha101 golden generation."""

from __future__ import annotations

import hashlib
import json
import math

from .oracle_runtime import (
    INPUT_MISSING,
    NO_LEGAL_BAR,
    NONFINITE,
    SW_L1_NOT_POINT_IN_TIME,
    SW_L2_NOT_POINT_IN_TIME,
    SW_L3_UNAVAILABLE,
    WINDOW_INCOMPLETE,
    Cell,
    OracleFailure,
    divide,
    finite,
    observed,
    unavailable,
)

FULL_INSTRUMENTS = tuple(f"{600000 + index:06d}.SH" for index in range(6))
EDGE_INSTRUMENTS = tuple(f"{300000 + index:06d}.SZ" for index in range(3))


class OraclePanel:
    def __init__(self, case: str) -> None:
        if case not in {"full_260d", "edge_65d", "pit_industry"}:
            raise ValueError(f"unknown oracle case {case}")
        self.case = case
        self.session_count = 260 if case == "full_260d" else 65
        self.instruments = FULL_INSTRUMENTS if case == "full_260d" else EDGE_INSTRUMENTS
        self._inputs: dict[str, tuple[tuple[Cell, ...], ...]] = {}

    def members(self, session: int) -> tuple[bool, ...]:
        return tuple(
            not (session < 3 and instrument == len(self.instruments) - 1)
            for instrument in range(len(self.instruments))
        )

    def input_matrix(self, name: str) -> tuple[tuple[Cell, ...], ...]:
        cached = self._inputs.get(name)
        if cached is not None:
            return cached
        matrix = tuple(
            tuple(
                self._input(name, session, instrument)
                for instrument in range(len(self.instruments))
            )
            for session in range(self.session_count)
        )
        self._inputs[name] = matrix
        return matrix

    def industry_groups(self, session: int, level: str) -> tuple[str | None, ...]:
        groups: list[str | None] = []
        for instrument in range(len(self.instruments)):
            if level == "subindustry":
                groups.append(None)
                continue
            if self.case == "pit_industry":
                if instrument == 0:
                    prefix = "future" if session == self.session_count - 1 else "old"
                    groups.append(f"{prefix}-l{1 if level == 'sector' else 2}")
                elif instrument == 1:
                    groups.append(f"visible-l{1 if level == 'sector' else 2}")
                else:
                    groups.append(None)
                continue
            if instrument == len(self.instruments) - 1:
                groups.append(None)
                continue
            label = ("group-a", "group-a", "group-b", "group-b", "singleton")[instrument]
            groups.append(f"{'l1' if level == 'sector' else 'l2'}-{label}")
        return tuple(groups)

    def input_content_hash(self) -> str:
        rows = []
        for session in range(self.session_count):
            for instrument, instrument_id in enumerate(self.instruments):
                bar = self._bar(session, instrument)
                rows.append(
                    [
                        session,
                        instrument_id,
                        *(
                            value.hex() if isinstance(value, float) else value
                            for value in bar.values()
                        ),
                        self.members(session)[instrument],
                        *(
                            self.industry_groups(session, level)[instrument]
                            for level in ("sector", "industry", "subindustry")
                        ),
                    ]
                )
        encoded = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def _input(self, name: str, session: int, instrument: int) -> Cell:
        if name.startswith("adv"):
            return self._adv(int(name.removeprefix("adv")), session, instrument)
        current = self._bar(session, instrument)
        if name in {"open", "high", "low", "close", "returns", "vwap"} and not current["legal"]:
            return unavailable(NO_LEGAL_BAR)
        if name == "returns":
            if session == 0:
                return unavailable(WINDOW_INCOMPLETE)
            prior = self._bar(session - 1, instrument)
            if not prior["legal"]:
                return unavailable(NO_LEGAL_BAR)
            return observed(
                divide(self._numeric(current, "close"), self._numeric(prior, "close")) - 1
            )
        if name == "vwap":
            try:
                raw_vwap = divide(
                    self._numeric(current, "amount"),
                    self._numeric(current, "volume"),
                )
                return observed(
                    finite(
                        raw_vwap
                        * divide(
                            self._numeric(current, "close"),
                            self._numeric(current, "raw_close"),
                        )
                    )
                )
            except OracleFailure as failure:
                return unavailable(failure.reason)
        key = {
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
            "cap": "cap",
        }[name]
        value = current[key]
        return (
            observed(self._numeric(current, key))
            if value is not None
            else unavailable(INPUT_MISSING)
        )

    def _adv(self, window: int, session: int, instrument: int) -> Cell:
        if session + 1 < window:
            return unavailable(WINDOW_INCOMPLETE)
        amounts = tuple(
            self._numeric(self._bar(day, instrument), "amount")
            for day in range(session - window + 1, session + 1)
        )
        try:
            return observed(finite(sum(amounts) / window))
        except (OracleFailure, OverflowError):
            return unavailable(NONFINITE)

    def _bar(self, session: int, instrument: int) -> dict[str, float | bool | None]:
        edge = self.case == "edge_65d"
        legal = not (edge and session == 52 and instrument == 0)
        action_scale = 0.5 if session >= (130 if self.case == "full_260d" else 32) else 1.0
        close = (
            1
            + 0.0015 * session
            + 0.002 * instrument
            + 0.055 * math.sin(session * (0.19 + 0.017 * instrument) + instrument * 1.37)
            + 0.027 * math.cos(session * (0.071 + 0.011 * instrument) + instrument * 0.43)
            + 0.035 * math.sin(session * 1.137 + instrument * 2.17)
            + 0.03 * ((-1.0) ** (session + instrument))
        )
        open_value = close * (
            1
            + 0.025 * math.sin(session * (0.23 + 0.019 * instrument) + instrument * 1.43)
            + 0.009 * math.cos(session * (0.097 + 0.013 * instrument) + instrument)
            + 0.018 * math.sin(session * 1.513 + instrument * 0.67)
        )
        spread = 0.013 + 0.001 * ((session + instrument) % 4)
        high = max(open_value, close) * (1 + spread)
        low = min(open_value, close) * (1 - spread)
        if edge and session == self.session_count - 1 and instrument == 2:
            open_value = high = low = close
        raw_close = (10 + close * 8 + instrument) * action_scale
        base_volume = (
            1_500_000
            + 2_777 * session
            + 650_000 * math.sin(session * (0.21 + 0.027 * instrument) + instrument * 1.19)
            + 450_000 * math.cos(session * (0.091 + 0.013 * instrument) + instrument * 0.53)
            + 3_000_000 * (1 + math.sin(session * 1.311 + instrument * 1.73))
        )
        volume = float(base_volume / action_scale)
        overflow = edge and instrument == 0 and session >= self.session_count - 2
        if overflow:
            volume = 1e308
        if edge and session == self.session_count - 1 and instrument == 1:
            volume = 0.0
        raw_vwap = raw_close * (
            1
            + 0.006 * math.cos(session * 0.13 + instrument * 0.91)
            + 0.003 * math.sin(session * 0.037 * (instrument + 1))
            + 0.004 * math.cos(session * 1.217 + instrument * 0.77)
        )
        amount = 1e308 if overflow else raw_vwap * volume
        return {
            "legal": legal,
            "open": open_value if legal else None,
            "high": high if legal else None,
            "low": low if legal else None,
            "close": close if legal else None,
            "raw_close": raw_close if legal else None,
            "volume": volume,
            "amount": amount,
            "cap": (
                12_000_000_000
                + 45_000_000 * session
                + 600_000_000 * instrument
                + 2_200_000_000 * math.sin(session * 0.027 + instrument * 1.29)
                + 1_100_000_000 * math.cos(session * 0.013 * (instrument + 1) + instrument * 0.4)
            ),
        }

    @staticmethod
    def unavailable_industry_reason(level: str) -> str:
        return {
            "sector": SW_L1_NOT_POINT_IN_TIME,
            "industry": SW_L2_NOT_POINT_IN_TIME,
            "subindustry": SW_L3_UNAVAILABLE,
        }[level]

    @staticmethod
    def _numeric(bar: dict[str, float | bool | None], key: str) -> float:
        value = bar[key]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError(f"oracle bar field {key} is unavailable")
        return float(value)
