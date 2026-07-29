from datetime import date

from astramind_mini.market_regime.domain.research_ranking import (
    RankingFeature,
    rank_industry,
)


def test_ranking_orders_complete_rows_and_applies_reversal_guard() -> None:
    features = tuple(_feature(index) for index in range(9))
    rows = rank_industry(
        features,
        market_features=features,
        evidence_cutoff=date(2026, 7, 28),
        lifecycle_stage="强势扩散",
    )

    assert len(rows) == 9
    assert all(row.coverage == 1 for row in rows)
    first_priority = rows[0].overall_priority
    last_priority = rows[-1].overall_priority
    assert first_priority is not None
    assert last_priority is not None
    assert first_priority >= last_priority
    crashing = next(row for row in rows if row.instrument_id == "000008.SZ")
    reversal_score = crashing.reversal_repair_score
    assert reversal_score is not None
    assert reversal_score >= 75
    assert crashing.overall_priority is not None and crashing.overall_priority <= 35
    assert crashing.research_label == "中性观察"


def test_coverage_below_sixty_percent_fails_closed() -> None:
    incomplete = _feature(1).__class__(
        **{
            **_feature(1).__dict__,
            "return_1d": None,
            "return_5d": None,
            "return_20d": None,
            "return_60d": None,
            "position_120d": None,
            "turnover_rate": None,
            "amount_share": None,
            "volatility_20d": None,
            "downside_volatility_20d": None,
            "drawdown_60d": None,
        }
    )
    rows = rank_industry(
        (incomplete,),
        market_features=tuple(_feature(index) for index in range(8)),
        evidence_cutoff=date(2026, 7, 28),
        lifecycle_stage="方向未明",
    )

    assert rows[0].coverage < 0.60
    assert rows[0].overall_priority is None
    assert rows[0].research_label == "数据不足"


def _feature(index: int) -> RankingFeature:
    crash = index == 8
    return RankingFeature(
        instrument_id=f"{index:06d}.SZ",
        instrument_name=f"样本{index}",
        industry_code="801010.SI",
        membership_effective_as_of=date(2021, 1, 1),
        return_1d=-0.12 if crash else index / 100,
        return_5d=-0.25 if crash else index / 50,
        return_20d=index / 40,
        return_60d=index / 30,
        position_120d=index / 10,
        turnover_rate=float(index),
        amount_share=index / 100,
        volatility_20d=(9 - index) / 100,
        downside_volatility_20d=(9 - index) / 100,
        drawdown_60d=-0.25 if crash else -index / 100,
        price_earnings_ttm=20 - index,
        price_book=5 - index / 4,
        dividend_yield_ttm=index / 10,
        holder_change_rate=-index / 100,
        lhb_attention=index / 10,
        below_ma_count=3 if crash else 0,
    )
