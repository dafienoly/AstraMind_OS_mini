from datetime import date, timedelta

from astramind_mini.market_regime.contracts import PriceCandle
from astramind_mini.market_regime.domain.etf_rotation import (
    CandidateInput,
    blocked_replay,
    build_target_draft,
    evaluate_candidate,
)

CUTOFF = date(2026, 7, 28)


def test_exact_candidate_passes_versioned_proxy_gates() -> None:
    prices = _prices()
    industry = tuple((item.trade_date, 100 * (1.0008**index)) for index, item in enumerate(prices))

    candidate = evaluate_candidate(
        CandidateInput(
            industry_code="801010.SI",
            industry_name="农林牧渔",
            lifecycle_stage="强势扩散",
            lifecycle_confidence="high",
            etf_code="159825.SZ",
            etf_name="农业ETF",
            mapping_tier="exact",
            mapping_eligible=True,
            mapping_active=True,
            decision_cutoff=CUTOFF,
            prices=prices,
            industry_closes=industry,
            latest_fund_share=100_000_000,
            master_listed=True,
        )
    )

    assert candidate.state == "eligible"
    assert candidate.overall_score is not None and candidate.overall_score >= 60
    assert candidate.spread_evidence_kind == "corwin_schultz_ohlc_proxy"
    assert candidate.tracking_evidence_kind == "sw_l1_exposure_proxy"
    assert candidate.price_conclusion == "趋势确认，未过热"


def test_stale_and_not_yet_effective_mapping_fail_closed() -> None:
    prices = _prices()[:-1]

    inactive = evaluate_candidate(_input(prices, mapping_active=False))
    stale = evaluate_candidate(_input(prices, mapping_active=True))

    assert inactive.state == "unavailable"
    assert inactive.rejection_reasons == ("mapping_not_effective_at_as_of",)
    assert stale.state == "stale"
    assert stale.rejection_reasons == ("latest_bar_before_decision_cutoff",)


def test_target_draft_caps_positions_and_never_creates_execution_contracts() -> None:
    candidate = evaluate_candidate(
        CandidateInput(
            industry_code="801010.SI",
            industry_name="农林牧渔",
            lifecycle_stage="强势扩散",
            lifecycle_confidence="high",
            etf_code="159825.SZ",
            etf_name="农业ETF",
            mapping_tier="exact",
            mapping_eligible=True,
            mapping_active=True,
            decision_cutoff=CUTOFF,
            prices=_prices(),
            industry_closes=tuple((item.trade_date, item.close) for item in _prices()),
            latest_fund_share=100_000_000,
            master_listed=True,
        )
    )

    second = candidate.model_copy(update={"industry_code": "801030.SI", "etf_code": "516020.SH"})
    target = build_target_draft((candidate, second, candidate))

    assert len(target.weights) == 2
    assert all(item.target_weight == 0.30 for item in target.weights)
    assert target.cash_weight == 0.40
    assert target.portfolio_target_created is False
    assert target.order_plan_created is False


def test_replay_discloses_candidate_frozen_history_and_withholds_performance() -> None:
    replay = blocked_replay(
        start_date=date(2021, 1, 4),
        end_date=CUTOFF,
        mapping_effective_from=date(2026, 7, 29),
    )

    assert replay.status == "candidate_frozen"
    assert replay.total_return is None
    assert replay.next_open_execution is True
    assert replay.promotion_evidence_eligible is False
    assert "performance_metrics_withheld" in replay.known_gaps


def _prices() -> tuple[PriceCandle, ...]:
    start = CUTOFF - timedelta(days=252)
    return tuple(
        PriceCandle(
            trade_date=start + timedelta(days=index),
            open=2.0 * (1.001**index),
            high=2.001 * (1.001**index),
            low=1.999 * (1.001**index),
            close=2.0 * (1.001**index),
            volume_lots=1_000_000,
            amount_cny=100_000_000,
        )
        for index in range(253)
    )


def _input(
    prices: tuple[PriceCandle, ...],
    *,
    mapping_active: bool,
) -> CandidateInput:
    return CandidateInput(
        industry_code="801010.SI",
        industry_name="农林牧渔",
        lifecycle_stage="强势扩散",
        lifecycle_confidence="high",
        etf_code="159825.SZ",
        etf_name="农业ETF",
        mapping_tier="exact",
        mapping_eligible=True,
        mapping_active=mapping_active,
        decision_cutoff=CUTOFF,
        prices=prices,
        industry_closes=tuple((item.trade_date, item.close) for item in prices),
        latest_fund_share=100_000_000,
        master_listed=True,
    )
