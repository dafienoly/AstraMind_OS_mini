from datetime import date, datetime, timedelta

import pytest

from astramind_mini.strategy_research.core import (
    CoreBoard,
    CoreDailyLiquidityObservation,
    CoreDiagnosticPool,
    CoreRiskObservation,
    CoreRiskStatus,
    CoreSecurityObservation,
    CoreUniverseDecision,
    CoreUniverseReason,
    core_universe_content_hash,
    evaluate_core_universe,
)

TZ = datetime.fromisoformat("2026-01-01T00:00:00+08:00").tzinfo
CUTOFF = datetime(2026, 1, 30, 18, 0, tzinfo=TZ)


def _sessions(count: int, *, end: date = date(2026, 1, 30)) -> tuple[date, ...]:
    return tuple(end - timedelta(days=offset) for offset in reversed(range(count)))


def _security(
    *,
    board: CoreBoard = CoreBoard.SSE_MAIN,
    listed_on: date = date(2025, 5, 24),
) -> CoreSecurityObservation:
    return CoreSecurityObservation(
        instrument_id="600000.SH",
        board=board,
        listed_on=listed_on,
        available_at=datetime(2025, 1, 1, 18, 0, tzinfo=TZ),
    )


def _risk(
    *,
    status: CoreRiskStatus = CoreRiskStatus.NORMAL,
    suspended: bool = False,
    available_at: datetime = datetime(2026, 1, 30, 17, 0, tzinfo=TZ),
) -> CoreRiskObservation:
    return CoreRiskObservation(
        instrument_id="600000.SH",
        effective_on=date(2026, 1, 30),
        status=status,
        suspended=suspended,
        available_at=available_at,
    )


def _liquidity(
    sessions: tuple[date, ...],
    *,
    zero_days: int = 0,
) -> tuple[CoreDailyLiquidityObservation, ...]:
    observations = []
    for index, trade_date in enumerate(sessions[-20:]):
        no_bar = index < zero_days
        observations.append(
            CoreDailyLiquidityObservation(
                instrument_id="600000.SH",
                trade_date=trade_date,
                amount_cny=None if no_bar else 40_000_000,
                has_legal_bar=not no_bar,
                available_at=datetime.combine(
                    trade_date,
                    datetime.min.time().replace(hour=18),
                    tzinfo=TZ,
                ),
            )
        )
    return tuple(observations)


def _evaluate(
    *,
    security: CoreSecurityObservation | None = None,
    risks: tuple[CoreRiskObservation, ...] | None = None,
    sessions: tuple[date, ...] | None = None,
    liquidity: tuple[CoreDailyLiquidityObservation, ...] | None = None,
) -> CoreUniverseDecision:
    common_sessions = sessions or _sessions(252)
    return evaluate_core_universe(
        security=security or _security(listed_on=common_sessions[0]),
        risk_history=risks if risks is not None else (_risk(),),
        liquidity_history=liquidity if liquidity is not None else _liquidity(common_sessions),
        common_sessions=common_sessions,
        decision_date=common_sessions[-1],
        cutoff_at=CUTOFF,
    )


def test_u0_eligible_decision_is_idempotent_and_keeps_zero_amount_sessions() -> None:
    sessions = _sessions(252)
    liquidity = _liquidity(sessions, zero_days=10)

    first = _evaluate(sessions=sessions, liquidity=liquidity)
    second = _evaluate(sessions=sessions, liquidity=tuple(reversed(liquidity)))

    assert first == second
    assert core_universe_content_hash((first,)) == core_universe_content_hash((second,))
    assert first.research_member is True
    assert first.new_risk_eligible is True
    assert first.diagnostic_pool == ()
    assert first.median_amount_20_cny == 20_000_000
    assert first.liquidity_observation_count == 20


@pytest.mark.parametrize(
    ("case", "expected_pool", "expected_reason", "research_member"),
    [
        (
            "new_stock",
            CoreDiagnosticPool.NEW_STOCK,
            CoreUniverseReason.INSUFFICIENT_SEASONING,
            True,
        ),
        (
            "bse",
            CoreDiagnosticPool.BSE,
            CoreUniverseReason.BSE_DIAGNOSTIC_ONLY,
            False,
        ),
        (
            "st",
            CoreDiagnosticPool.RISK_STATE,
            CoreUniverseReason.ST_OR_STAR_ST,
            True,
        ),
        (
            "unknown",
            CoreDiagnosticPool.RISK_STATE,
            CoreUniverseReason.RISK_STATUS_UNKNOWN,
            True,
        ),
        (
            "suspended",
            CoreDiagnosticPool.SUSPENDED,
            CoreUniverseReason.SUSPENDED,
            True,
        ),
        (
            "short_liquidity",
            CoreDiagnosticPool.COVERAGE,
            CoreUniverseReason.INSUFFICIENT_LIQUIDITY_HISTORY,
            True,
        ),
        (
            "low_liquidity",
            CoreDiagnosticPool.COVERAGE,
            CoreUniverseReason.MEDIAN_AMOUNT_BELOW_FLOOR,
            True,
        ),
    ],
)
def test_research_membership_new_risk_and_diagnostic_pools_are_separate(
    case: str,
    expected_pool: CoreDiagnosticPool,
    expected_reason: CoreUniverseReason,
    research_member: bool,
) -> None:
    sessions = _sessions(252)
    security = _security(listed_on=sessions[0])
    risks: tuple[CoreRiskObservation, ...] = (_risk(),)
    liquidity = _liquidity(sessions)

    if case == "new_stock":
        security = _security(listed_on=sessions[1])
    elif case == "bse":
        security = _security(board=CoreBoard.BSE, listed_on=sessions[0])
    elif case == "st":
        risks = (_risk(status=CoreRiskStatus.ST),)
    elif case == "unknown":
        risks = ()
    elif case == "suspended":
        risks = (_risk(suspended=True),)
    elif case == "short_liquidity":
        sessions = _sessions(19)
        security = _security(listed_on=date(2025, 1, 1))
        liquidity = _liquidity(sessions)
    elif case == "low_liquidity":
        liquidity = _liquidity(sessions, zero_days=11)

    decision = _evaluate(
        security=security,
        risks=risks,
        sessions=sessions,
        liquidity=liquidity,
    )

    assert decision.research_member is research_member
    assert decision.new_risk_eligible is False
    assert expected_pool in decision.diagnostic_pool
    assert expected_reason in decision.reason_codes


def test_future_risk_revision_is_not_visible_to_historical_cutoff() -> None:
    sessions = _sessions(252)
    decision = _evaluate(
        sessions=sessions,
        risks=(
            _risk(available_at=datetime(2026, 1, 30, 17, 0, tzinfo=TZ)),
            _risk(
                status=CoreRiskStatus.STAR_ST,
                available_at=datetime(2026, 2, 2, 9, 0, tzinfo=TZ),
            ),
        ),
    )

    assert decision.new_risk_eligible is True
    assert CoreUniverseReason.ST_OR_STAR_ST not in decision.reason_codes
    changed = _evaluate(sessions=sessions, risks=(_risk(status=CoreRiskStatus.ST),))
    assert core_universe_content_hash((decision,)) != core_universe_content_hash((changed,))
