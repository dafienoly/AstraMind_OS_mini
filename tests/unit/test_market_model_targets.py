import pytest

from astramind_mini.strategy_research.market_models.targets import (
    EtfWeightCandidate,
    etf_inverse_volatility_weights,
    etf_net_excess_target,
    excess_return,
    industry_research_target,
    lifecycle_stage_label,
    shrunk_industry_rank,
)


def test_excess_targets_use_the_same_simple_return_clock() -> None:
    assert excess_return(
        asset_start=100,
        asset_end=110,
        benchmark_start=200,
        benchmark_end=210,
    ) == pytest.approx(0.05)
    assert etf_net_excess_target(
        etf_start=1.0,
        etf_end=1.08,
        official_benchmark_start=100,
        official_benchmark_end=105,
        round_trip_cost_rate=0.003,
    ) == pytest.approx(0.027)


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        (
            {
                "future_20d_excess_percentile": 0.20,
                "future_20d_max_drawdown": -0.08,
                "current_low_participation_percentile": 0.90,
                "current_strong_participation_percentile": 0.10,
            },
            "obvious_decline",
        ),
        (
            {
                "future_20d_excess_percentile": 0.65,
                "future_20d_max_drawdown": -0.03,
                "current_low_participation_percentile": 0.75,
                "current_strong_participation_percentile": 0.20,
            },
            "low_position_repair",
        ),
        (
            {
                "future_20d_excess_percentile": 0.72,
                "future_20d_max_drawdown": -0.03,
                "current_low_participation_percentile": 0.40,
                "current_strong_participation_percentile": 0.60,
            },
            "strong_expansion",
        ),
        (
            {
                "future_20d_excess_percentile": 0.50,
                "future_20d_max_drawdown": -0.03,
                "current_low_participation_percentile": 0.90,
                "current_strong_participation_percentile": 0.10,
            },
            "extreme_low",
        ),
        (
            {
                "future_20d_excess_percentile": 0.30,
                "future_20d_max_drawdown": -0.03,
                "current_low_participation_percentile": 0.40,
                "current_strong_participation_percentile": 0.60,
            },
            "decline_watch",
        ),
        (
            {
                "future_20d_excess_percentile": 0.50,
                "future_20d_max_drawdown": -0.03,
                "current_low_participation_percentile": 0.40,
                "current_strong_participation_percentile": 0.60,
            },
            "unclear",
        ),
    ],
)
def test_lifecycle_label_precedence_is_unique(
    arguments: dict[str, float],
    expected: str,
) -> None:
    assert lifecycle_stage_label(**arguments) == expected


def test_ranking_target_and_small_industry_shrinkage() -> None:
    assert industry_research_target(
        future_20d_within_industry_rank=0.8,
        future_60d_within_industry_rank=0.4,
    ) == pytest.approx(0.68)
    assert shrunk_industry_rank(
        industry_rank=1.0,
        market_rank=0.4,
        industry_sample_size=5,
    ) == pytest.approx(0.6)
    assert shrunk_industry_rank(
        industry_rank=1.0,
        market_rank=0.4,
        industry_sample_size=0,
    ) == pytest.approx(0.4)


def test_etf_weights_reject_correlation_and_respect_caps() -> None:
    result = etf_inverse_volatility_weights(
        (
            EtfWeightCandidate("510001.SH", 0.08, 0.10),
            EtfWeightCandidate("510002.SH", 0.07, 0.11),
            EtfWeightCandidate("510003.SH", 0.06, 0.20),
        ),
        correlations={
            ("510001.SH", "510002.SH"): 0.90,
            ("510001.SH", "510003.SH"): 0.20,
        },
    )

    assert [item[0] for item in result.weights] == ["510001.SH", "510003.SH"]
    assert result.rejected_correlated == ("510002.SH",)
    assert sum(item[1] for item in result.weights) == pytest.approx(0.60)
    assert max(item[1] for item in result.weights) <= 0.35
    assert result.cash_weight == pytest.approx(0.40)


def test_single_etf_keeps_unallocated_cash() -> None:
    result = etf_inverse_volatility_weights(
        (EtfWeightCandidate("510001.SH", 0.08, 0.10),),
        correlations={},
    )

    assert result.weights == (("510001.SH", 0.35),)
    assert result.cash_weight == pytest.approx(0.65)
