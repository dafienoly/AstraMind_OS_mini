from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from astramind_mini.strategy_research.application.identity import research_hash
from astramind_mini.strategy_research.core.calendar import freeze_core_common_calendar
from astramind_mini.strategy_research.core.contracts import CoreUniverseDecision
from astramind_mini.strategy_research.core.labels import (
    CoreForwardPriceObservation,
    CoreForwardReturnLabelBatch,
    CoreForwardReturnLabelRow,
    CoreForwardReturnLabelSpec,
    CoreLabelHorizon,
    CoreLabelReason,
    build_core_forward_return_label_batch,
)

HASH = "sha256:" + "1" * 64
SESSIONS = tuple(date(2025, 1, 1) + timedelta(days=index) for index in range(65))
T0 = datetime(2025, 1, 1, 16, tzinfo=UTC)
AVAILABLE = datetime(2025, 3, 10, 16, tzinfo=UTC)
CALENDAR = freeze_core_common_calendar(calendar_id="label-fixture-v1", sessions=SESSIONS)


def _decision(instrument: str, *, member: bool = True) -> CoreUniverseDecision:
    return CoreUniverseDecision(
        instrument_id=instrument,
        decision_date=SESSIONS[0],
        input_cutoff=T0,
        universe_version="U0-v1",
        research_member=member,
        new_risk_eligible=member,
        diagnostic_pool=(),
        reason_codes=(),
        listed_common_sessions=300,
        liquidity_observation_count=20,
        median_amount_20_cny=30_000_000,
    )


def _price(
    instrument: str,
    session: int,
    *,
    open_price: float | None = None,
    close_price: float | None = None,
    available_at: datetime = AVAILABLE,
) -> CoreForwardPriceObservation:
    return CoreForwardPriceObservation(
        instrument_id=instrument,
        trade_date=SESSIONS[session],
        research_open=open_price,
        research_close=close_price,
        available_at=available_at,
        source_record_hash=HASH,
    )


def _build(
    *,
    horizon: CoreLabelHorizon,
    universe: tuple[CoreUniverseDecision, ...],
    prices: tuple[CoreForwardPriceObservation, ...],
    snapshot_as_of: datetime = AVAILABLE,
    cutoff: datetime = AVAILABLE,
):
    return build_core_forward_return_label_batch(
        spec=CoreForwardReturnLabelSpec(horizon=horizon),
        decision_date=SESSIONS[0],
        common_calendar=CALENDAR,
        universe_rows=universe,
        prices=prices,
        label_data_snapshot_id="label-snapshot",
        label_data_snapshot_content_hash=HASH,
        label_data_snapshot_as_of=snapshot_as_of,
        label_available_cutoff=cutoff,
    )


def test_h20_h60_use_t1_open_and_exact_horizon_close_and_maturity() -> None:
    universe = (_decision("A"), _decision("B"))
    prices = (
        _price("A", 1, open_price=10.0),
        _price("A", 20, close_price=12.0),
        _price("A", 60, close_price=9.0),
        _price("B", 1, open_price=10.0),
        _price("B", 20, close_price=11.0),
        _price("B", 60, close_price=10.0),
    )
    h20 = _build(horizon=CoreLabelHorizon.H20, universe=universe, prices=prices)
    h60 = _build(horizon=CoreLabelHorizon.H60, universe=universe, prices=prices)
    assert h20.rows[0].absolute_return == pytest.approx(0.2)
    assert h60.rows[0].absolute_return == pytest.approx(-0.1)
    assert (h20.entry_date, h20.horizon_close_date) == (SESSIONS[1], SESSIONS[20])
    assert h60.horizon_close_date == SESSIONS[60]

    immature = _build(
        horizon=CoreLabelHorizon.H60,
        universe=universe,
        prices=prices,
        snapshot_as_of=AVAILABLE,
        cutoff=AVAILABLE - timedelta(microseconds=1),
    )
    assert not immature.matured
    assert {item.reason_code for item in immature.rows} == {CoreLabelReason.NOT_MATURED}


def test_nonmember_is_audit_only_and_percentiles_use_valid_members() -> None:
    universe = tuple(
        _decision(instrument, member=instrument != "E") for instrument in ("A", "B", "C", "D", "E")
    )
    prices = tuple(
        observation
        for instrument, terminal in (("A", 12.0), ("B", 11.0), ("C", 11.0), ("E", 19.0))
        for observation in (
            _price(instrument, 1, open_price=10.0),
            _price(instrument, 20, close_price=terminal),
        )
    )
    prices += (_price("D", 1, open_price=10.0),)
    batch = _build(
        horizon=CoreLabelHorizon.H20,
        universe=universe,
        prices=prices,
    )
    rows = {item.instrument_id: item for item in batch.rows}
    assert [rows[key].percentile for key in ("A", "B", "C")] == [1.0, 0.25, 0.25]
    assert rows["D"].reason_code == CoreLabelReason.HORIZON_CLOSE_MISSING
    assert rows["E"].reason_code == CoreLabelReason.NOT_RESEARCH_MEMBER
    assert (
        batch.n_universe_rows,
        batch.n_research_members,
        batch.n_valid_returns,
        batch.label_coverage,
    ) == (5, 4, 3, 0.75)


def test_future_price_append_does_not_change_a_frozen_cutoff() -> None:
    universe = (_decision("A"), _decision("B"))
    base = (
        _price("A", 1, open_price=10.0),
        _price("A", 20, close_price=12.0),
        _price("B", 1, open_price=10.0),
        _price("B", 20, close_price=11.0),
    )
    original = _build(
        horizon=CoreLabelHorizon.H20,
        universe=universe,
        prices=base,
    )
    appended = _build(
        horizon=CoreLabelHorizon.H20,
        universe=universe,
        prices=(
            *base,
            _price(
                "A",
                20,
                close_price=99.0,
                available_at=AVAILABLE + timedelta(seconds=1),
            ),
        ),
    )
    assert appended == original

    later_maturity_cutoff = _build(
        horizon=CoreLabelHorizon.H20,
        universe=universe,
        prices=(
            *base,
            _price(
                "A",
                20,
                close_price=88.0,
                available_at=AVAILABLE + timedelta(microseconds=1),
            ),
        ),
        snapshot_as_of=AVAILABLE,
        cutoff=AVAILABLE + timedelta(seconds=1),
    )
    assert later_maturity_cutoff.rows == original.rows


def test_overflowing_forward_return_fails_closed() -> None:
    universe = (_decision("A"), _decision("B"))
    prices = (
        _price("A", 1, open_price=1e-308),
        _price("A", 20, close_price=1e308),
        _price("B", 1, open_price=10.0),
        _price("B", 20, close_price=11.0),
    )
    with pytest.raises(ValueError, match="finite"):
        _build(
            horizon=CoreLabelHorizon.H20,
            universe=universe,
            prices=prices,
        )


def _rehash_batch(data: dict[str, object]) -> dict[str, object]:
    normalized = dict(data)
    normalized["spec"] = CoreForwardReturnLabelSpec.model_validate(data["spec"])
    normalized["common_calendar"] = freeze_core_common_calendar(
        calendar_id=data["common_calendar"]["calendar_id"],  # type: ignore[index]
        sessions=data["common_calendar"]["sessions"],  # type: ignore[index]
    )
    normalized["universe_rows"] = tuple(
        CoreUniverseDecision.model_validate(item)
        for item in data["universe_rows"]  # type: ignore[union-attr]
    )
    normalized["rows"] = tuple(
        CoreForwardReturnLabelRow.model_validate(item)
        for item in data["rows"]  # type: ignore[union-attr]
    )
    draft = CoreForwardReturnLabelBatch.model_construct(**normalized)
    body = {
        "spec": draft.spec,
        "decision_date": draft.decision_date,
        "common_calendar": draft.common_calendar,
        "entry_date": draft.entry_date,
        "horizon_close_date": draft.horizon_close_date,
        "decision_universe_content_hash": draft.decision_universe_content_hash,
        "universe_rows": draft.universe_rows,
        "label_data_snapshot_id": draft.label_data_snapshot_id,
        "label_data_snapshot_content_hash": draft.label_data_snapshot_content_hash,
        "label_data_snapshot_as_of": draft.label_data_snapshot_as_of,
        "label_available_cutoff": draft.label_available_cutoff,
        "matured": draft.matured,
        "n_universe_rows": draft.n_universe_rows,
        "n_research_members": draft.n_research_members,
        "n_valid_returns": draft.n_valid_returns,
        "label_coverage": draft.label_coverage,
        "rows": draft.rows,
    }
    content_hash = research_hash({"schema": "core-forward-return-label-batch-v1", **body})
    data["content_hash"] = content_hash
    data["batch_id"] = f"core-label-batch:{content_hash.removeprefix('sha256:')}"
    return data


def test_bound_calendar_and_fully_rehashed_label_attacks_fail_closed() -> None:
    batch = _build(
        horizon=CoreLabelHorizon.H20,
        universe=(_decision("A"), _decision("B")),
        prices=(
            _price("A", 1, open_price=10.0),
            _price("A", 20, close_price=12.0),
            _price("B", 1, open_price=10.0),
            _price("B", 20, close_price=11.0),
        ),
    )
    changed_sessions = list(SESSIONS)
    changed_sessions[30] = date(2030, 1, 1)
    changed_sessions.sort()
    changed_calendar = freeze_core_common_calendar(
        calendar_id=CALENDAR.calendar_id,
        sessions=changed_sessions,
    )
    changed = batch.model_dump()
    changed["common_calendar"] = changed_calendar.model_dump()
    changed_batch = CoreForwardReturnLabelBatch.model_validate(_rehash_batch(changed))
    assert changed_batch.content_hash != batch.content_hash

    percentile_attack = batch.model_dump()
    rows = list(percentile_attack["rows"])
    rows[0] = {**rows[0], "percentile": 0.25}
    percentile_attack["rows"] = tuple(rows)
    with pytest.raises(ValueError, match="recomputed average rank"):
        CoreForwardReturnLabelBatch.model_validate(_rehash_batch(percentile_attack))

    endpoint_attack = batch.model_dump()
    endpoint_attack["entry_date"] = SESSIONS[2]
    with pytest.raises(ValueError, match="entry or horizon endpoint"):
        CoreForwardReturnLabelBatch.model_validate(_rehash_batch(endpoint_attack))

    maturity_attack = batch.model_dump()
    maturity_attack["matured"] = False
    maturity_attack["n_valid_returns"] = 0
    maturity_attack["label_coverage"] = 0.0
    maturity_attack["rows"] = tuple(
        {
            **row,
            "absolute_return": None,
            "percentile": None,
            "reason_code": CoreLabelReason.NOT_MATURED,
        }
        for row in maturity_attack["rows"]
    )
    with pytest.raises(ValueError, match="maturity"):
        CoreForwardReturnLabelBatch.model_validate(_rehash_batch(maturity_attack))
