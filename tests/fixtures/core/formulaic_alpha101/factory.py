"""Small deterministic panels used by the Alpha101 fidelity tests."""

from __future__ import annotations

import hashlib
import json
import math
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.contracts import DatasetRef, DataSnapshot
from astramind_mini.strategy_research.core.contracts import (
    CoreDatasetSlice,
    CoreDiagnosticPool,
    CoreInputLayer,
    CoreInputSnapshot,
    CoreUniverseDecision,
    CoreUniverseReason,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.inputs import (
    Alpha101DailyObservation,
    Alpha101Panel,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.reference import (
    scalar_reference_source_hash,
)
from astramind_mini.strategy_research.core.formulaic_alpha101.universe import (
    Alpha101UniverseHistory,
    freeze_alpha101_universe_history,
)
from astramind_mini.strategy_research.core.identity import freeze_core_input_snapshot
from astramind_mini.strategy_research.core.semantics import IndustryMembershipObservation
from astramind_mini.strategy_research.core.universe import core_universe_content_hash

SHANGHAI = ZoneInfo("Asia/Shanghai")
HASH_A = "sha256:" + "a" * 64
HASH_B = "sha256:" + "b" * 64
HASH_C = "sha256:" + "c" * 64
BAR_DATASET_NAME = "alpha101_bars_fixture"
INDUSTRY_DATASET_NAME = "alpha101_industry_fixture"
FULL_INSTRUMENTS = tuple(f"{600000 + index:06d}.SH" for index in range(6))
EDGE_INSTRUMENTS = tuple(f"{300000 + index:06d}.SZ" for index in range(3))
CALENDAR_FIXTURE = Path(__file__).with_name("sse_szse_common_calendar_2025_2026.json")


def fixture_generator_source_hash() -> str:
    digest = hashlib.sha256(Path(__file__).read_bytes())
    digest.update(scalar_reference_source_hash().encode())
    return "sha256:" + digest.hexdigest()


def common_sessions(count: int, *, start: date = date(2025, 1, 2)) -> tuple[date, ...]:
    sessions = official_common_sessions()
    try:
        position = sessions.index(start)
    except ValueError as error:
        raise ValueError("fixture start must be a declared common trading session") from error
    selected = sessions[position : position + count]
    if len(selected) != count:
        raise ValueError("fixture calendar does not cover the requested session count")
    return selected


def official_common_sessions() -> tuple[date, ...]:
    specification = json.loads(CALENDAR_FIXTURE.read_text(encoding="utf-8"))
    first = date.fromisoformat(specification["first_date"])
    last = date.fromisoformat(specification["last_date"])
    closures: set[date] = set()
    for raw_start, raw_end in specification["closure_ranges"]:
        current = date.fromisoformat(raw_start)
        end = date.fromisoformat(raw_end)
        while current <= end:
            closures.add(current)
            current += timedelta(days=1)
    sessions = []
    current = first
    while current <= last:
        if current.weekday() < 5 and current not in closures:
            sessions.append(current)
        current += timedelta(days=1)
    if len(sessions) != specification["expected_open_session_count"]:
        raise ValueError("official calendar fixture session count drifted")
    return tuple(sessions)


def full_panel(
    *,
    session_count: int = 260,
    drop_session_index: int | None = None,
    flip_membership_at: tuple[int, int] | None = None,
    late_bar_at: tuple[int, int] | None = None,
) -> Alpha101Panel:
    selected = list(common_sessions(session_count))
    if drop_session_index is not None:
        del selected[drop_session_index]
    sessions = tuple(selected)
    return _panel(
        sessions=sessions,
        instruments=FULL_INSTRUMENTS,
        edge=False,
        action_day=130,
        industries=_industries(FULL_INSTRUMENTS, sessions[0]),
        flip_membership_at=flip_membership_at,
        late_bar_at=late_bar_at,
    )


def edge_panel() -> Alpha101Panel:
    sessions = common_sessions(65, start=date(2026, 1, 5))
    return _panel(
        sessions=sessions,
        instruments=EDGE_INSTRUMENTS,
        edge=True,
        action_day=32,
        industries=_industries(EDGE_INSTRUMENTS, sessions[0]),
    )


def pit_panel(*, late_industry: bool = False) -> Alpha101Panel:
    sessions = common_sessions(65, start=date(2026, 4, 1))
    industries = list(
        pit_industries(
            EDGE_INSTRUMENTS[0],
            first_session=sessions[0],
            final_session=sessions[-1],
            late=late_industry,
        )
    )
    industries.append(
        IndustryMembershipObservation(
            instrument_id=EDGE_INSTRUMENTS[1],
            valid_from=sessions[0],
            sw_l1="visible-l1",
            sw_l2="visible-l2",
            sw_l3=None,
            available_at=datetime.combine(sessions[0], time(9), tzinfo=SHANGHAI),
            source_record_hash=HASH_A,
        )
    )
    return _panel(
        sessions=sessions,
        instruments=EDGE_INSTRUMENTS,
        edge=False,
        action_day=32,
        industries=industries,
    )


def core_input(
    panel: Alpha101Panel,
    *,
    dataset_cutoff_time: time = time(18),
) -> CoreInputSnapshot:
    decision_date = panel.sessions[-1]
    cutoff = datetime.combine(decision_date, time(18), tzinfo=SHANGHAI)
    available = datetime.combine(
        decision_date,
        dataset_cutoff_time,
        tzinfo=SHANGHAI,
    )
    bar_dataset = DatasetRef(
        dataset_name=panel.bar_dataset_name,
        dataset_version="fixture-v1",
        schema_version="1.0.0",
        content_hash=panel.bar_content_hash,
    )
    industry_dataset = DatasetRef(
        dataset_name=panel.industry_dataset_name,
        dataset_version="fixture-v1",
        schema_version="1.0.0",
        content_hash=panel.industry_content_hash,
    )
    history = panel.universe_history.manifest
    history_dataset = DatasetRef(
        dataset_name=history.dataset_name,
        dataset_version=history.manifest_version,
        schema_version="1.0.0",
        content_hash=history.history_content_hash,
    )
    snapshot = DataSnapshot(
        snapshot_id="snapshot:alpha101-fixture",
        as_of=cutoff,
        datasets=(bar_dataset, industry_dataset, history_dataset),
        created_at=cutoff,
        code_identity="formulaic-alpha101-fixture-v1",
    )
    bar_slice = CoreDatasetSlice(
        dataset_name=bar_dataset.dataset_name,
        dataset_version=bar_dataset.dataset_version,
        schema_version=bar_dataset.schema_version,
        content_hash=bar_dataset.content_hash,
        row_count=len(panel.sessions) * len(panel.instruments),
        min_market_date=panel.sessions[0],
        max_market_date=decision_date,
        max_available_at=available,
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    industry_slice = CoreDatasetSlice(
        dataset_name=industry_dataset.dataset_name,
        dataset_version=industry_dataset.dataset_version,
        schema_version=industry_dataset.schema_version,
        content_hash=industry_dataset.content_hash,
        row_count=len(panel.industries),
        min_market_date=panel.sessions[0],
        max_market_date=decision_date,
        max_available_at=available,
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    history_slice = CoreDatasetSlice(
        dataset_name=history_dataset.dataset_name,
        dataset_version=history_dataset.dataset_version,
        schema_version=history_dataset.schema_version,
        content_hash=history_dataset.content_hash,
        row_count=history.row_count,
        min_market_date=history.min_decision_date,
        max_market_date=history.max_decision_date,
        max_available_at=history.max_input_cutoff,
        input_layer=CoreInputLayer.COMPLETED_DAILY,
        sealed=True,
    )
    return freeze_core_input_snapshot(
        data_snapshot=snapshot,
        decision_date=decision_date,
        cutoff_at=cutoff,
        common_calendar_id="sse-szse-common-fixture-v1",
        common_sessions=panel.sessions,
        universe_content_hash=core_universe_content_hash(
            panel.universe_history.current_decisions()
        ),
        datasets=(bar_slice, industry_slice, history_slice),
    )


def pit_industries(
    instrument: str,
    *,
    first_session: date,
    final_session: date,
    late: bool = False,
) -> tuple[IndustryMembershipObservation, ...]:
    old_available = datetime.combine(first_session, time(9), tzinfo=SHANGHAI)
    future_available = datetime.combine(
        final_session + timedelta(days=1) if late else final_session,
        time(17),
        tzinfo=SHANGHAI,
    )
    return (
        IndustryMembershipObservation(
            instrument_id=instrument,
            valid_from=first_session,
            sw_l1="old-l1",
            sw_l2="old-l2",
            sw_l3=None,
            available_at=old_available,
            source_record_hash=HASH_A,
        ),
        IndustryMembershipObservation(
            instrument_id=instrument,
            valid_from=first_session,
            sw_l1="future-l1",
            sw_l2="future-l2",
            sw_l3=None,
            available_at=future_available,
            source_record_hash=HASH_B,
        ),
    )


def _panel(
    *,
    sessions: tuple[date, ...],
    instruments: tuple[str, ...],
    edge: bool,
    action_day: int,
    industries: list[IndustryMembershipObservation] | tuple[IndustryMembershipObservation, ...],
    flip_membership_at: tuple[int, int] | None = None,
    late_bar_at: tuple[int, int] | None = None,
) -> Alpha101Panel:
    universe_history = _universe_history(
        sessions,
        instruments,
        flip_membership_at=flip_membership_at,
    )
    return Alpha101Panel(
        common_sessions=sessions,
        universe_history=universe_history,
        bar_dataset_name=BAR_DATASET_NAME,
        industry_dataset_name=INDUSTRY_DATASET_NAME,
        instruments=instruments,
        observations=_observations(
            sessions,
            instruments,
            edge=edge,
            action_day=action_day,
            late_bar_at=late_bar_at,
        ),
        industries=industries,
    )


def _universe_history(
    sessions: tuple[date, ...],
    instruments: tuple[str, ...],
    *,
    flip_membership_at: tuple[int, int] | None,
) -> Alpha101UniverseHistory:
    decisions = []
    for day_index, day in enumerate(sessions):
        cutoff = datetime.combine(day, time(18), tzinfo=SHANGHAI)
        for instrument_index, instrument in enumerate(instruments):
            member = not (day_index < 3 and instrument_index == len(instruments) - 1)
            if flip_membership_at == (day_index, instrument_index):
                member = not member
            decisions.append(
                CoreUniverseDecision(
                    instrument_id=instrument,
                    decision_date=day,
                    input_cutoff=cutoff,
                    universe_version="U0-v1",
                    research_member=member,
                    new_risk_eligible=member,
                    diagnostic_pool=(() if member else (CoreDiagnosticPool.NEW_STOCK,)),
                    reason_codes=(() if member else (CoreUniverseReason.INSUFFICIENT_SEASONING,)),
                    listed_common_sessions=day_index + 1,
                    liquidity_observation_count=min(day_index + 1, 20),
                    median_amount_20_cny=30_000_000 if member else None,
                )
            )
    return freeze_alpha101_universe_history(
        common_sessions=sessions,
        instruments=instruments,
        decisions=decisions,
    )


def _observations(
    sessions: tuple[date, ...],
    instruments: tuple[str, ...],
    *,
    edge: bool,
    action_day: int,
    late_bar_at: tuple[int, int] | None,
) -> tuple[Alpha101DailyObservation, ...]:
    result = []
    for day_index, day in enumerate(sessions):
        for instrument_index, instrument in enumerate(instruments):
            legal = not (edge and day_index == 52 and instrument_index == 0)
            action_scale = 0.5 if day_index >= action_day else 1.0
            trend = 1 + 0.0015 * day_index + 0.002 * instrument_index
            wave = (
                0.055
                * math.sin(day_index * (0.19 + 0.017 * instrument_index) + instrument_index * 1.37)
                + 0.027
                * math.cos(day_index * (0.071 + 0.011 * instrument_index) + instrument_index * 0.43)
                + 0.035 * math.sin(day_index * 1.137 + instrument_index * 2.17)
                + 0.03 * ((-1.0) ** (day_index + instrument_index))
            )
            close = trend + wave
            open_value = close * (
                1
                + 0.025
                * math.sin(day_index * (0.23 + 0.019 * instrument_index) + instrument_index * 1.43)
                + 0.009
                * math.cos(day_index * (0.097 + 0.013 * instrument_index) + instrument_index)
                + 0.018 * math.sin(day_index * 1.513 + instrument_index * 0.67)
            )
            spread = 0.013 + 0.001 * ((day_index + instrument_index) % 4)
            high = max(open_value, close) * (1 + spread)
            low = min(open_value, close) * (1 - spread)
            if edge and day_index == len(sessions) - 1 and instrument_index == 2:
                open_value = high = low = close
            raw_close = (10 + close * 8 + instrument_index) * action_scale
            base_volume = (
                1_500_000
                + 2_777 * day_index
                + 650_000
                * math.sin(day_index * (0.21 + 0.027 * instrument_index) + instrument_index * 1.19)
                + 450_000
                * math.cos(day_index * (0.091 + 0.013 * instrument_index) + instrument_index * 0.53)
                + 3_000_000 * (1 + math.sin(day_index * 1.311 + instrument_index * 1.73))
            )
            volume = float(base_volume / action_scale)
            overflow_amount = edge and instrument_index == 0 and day_index >= len(sessions) - 2
            if overflow_amount:
                volume = 1e308
            if edge and day_index == len(sessions) - 1 and instrument_index == 1:
                volume = 0.0
            raw_vwap = raw_close * (
                1
                + 0.006 * math.cos(day_index * 0.13 + instrument_index * 0.91)
                + 0.003 * math.sin(day_index * 0.037 * (instrument_index + 1))
                + 0.004 * math.cos(day_index * 1.217 + instrument_index * 0.77)
            )
            amount = 1e308 if overflow_amount else raw_vwap * volume
            result.append(
                Alpha101DailyObservation(
                    instrument_id=instrument,
                    trade_date=day,
                    available_at=datetime.combine(
                        day,
                        (time(18, 1) if late_bar_at == (day_index, instrument_index) else time(16)),
                        tzinfo=SHANGHAI,
                    ),
                    has_legal_bar=legal,
                    research_open_index=open_value if legal else None,
                    research_high_index=high if legal else None,
                    research_low_index=low if legal else None,
                    research_close_index=close if legal else None,
                    raw_close_cny=raw_close if legal else None,
                    raw_volume_shares=volume,
                    raw_amount_cny=amount,
                    total_market_cap_cny=(
                        12_000_000_000
                        + 45_000_000 * day_index
                        + 600_000_000 * instrument_index
                        + 2_200_000_000 * math.sin(day_index * 0.027 + instrument_index * 1.29)
                        + 1_100_000_000
                        * math.cos(
                            day_index * 0.013 * (instrument_index + 1) + instrument_index * 0.4
                        )
                    ),
                )
            )
    return tuple(result)


def _industries(
    instruments: tuple[str, ...],
    first_session: date,
) -> tuple[IndustryMembershipObservation, ...]:
    result = []
    for index, instrument in enumerate(instruments):
        if index == len(instruments) - 1:
            l1 = l2 = None
        else:
            group = ("group-a", "group-a", "group-b", "group-b", "singleton")[index]
            l1 = f"l1-{group}"
            l2 = f"l2-{group}"
        result.append(
            IndustryMembershipObservation(
                instrument_id=instrument,
                valid_from=first_session,
                sw_l1=l1,
                sw_l2=l2,
                sw_l3=None,
                available_at=datetime.combine(first_session, time(9), tzinfo=SHANGHAI),
                source_record_hash=HASH_A,
            )
        )
    return tuple(result)


__all__ = [
    "BAR_DATASET_NAME",
    "EDGE_INSTRUMENTS",
    "FULL_INSTRUMENTS",
    "INDUSTRY_DATASET_NAME",
    "SHANGHAI",
    "common_sessions",
    "core_input",
    "edge_panel",
    "fixture_generator_source_hash",
    "full_panel",
    "official_common_sessions",
    "pit_industries",
    "pit_panel",
]
