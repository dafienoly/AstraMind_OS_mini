from __future__ import annotations

from astramind_mini.strategy_research.core.feature_selection import (
    CoreSubfoldRankICEvidence,
    benjamini_hochberg,
    complete_linkage_clusters,
    selection_seed,
    splitmix64_next,
    subfold_direction_consistent,
    summarize_subfold_rankic,
)


def test_splitmix64_seed_and_first_starts_match_frozen_vector() -> None:
    seed = selection_seed("F", "1.0.0", "H20", "fold-001")
    assert seed == 1290558554154497014
    state = seed
    starts = []
    for _ in range(10):
        state, output = splitmix64_next(state)
        starts.append(output % 180)
    assert starts == [19, 127, 143, 153, 100, 162, 119, 51, 175, 73]


def test_bh_uses_only_finite_family_and_stable_id_ties() -> None:
    result = benjamini_hochberg({"B": 0.02, "A": 0.02, "C": 0.074, "D": 0.20, "NO_P": None})
    assert list(result) == ["A", "B", "C", "D"]
    assert [result[key][2] for key in ("A", "B", "C", "D")] == [
        True,
        True,
        True,
        False,
    ]
    assert result["C"][1] == 0.07500000000000001
    assert "NO_P" not in result


def test_complete_linkage_prevents_chain_merge_and_unknown_distance() -> None:
    distances = {
        frozenset(("A", "B")): 0.1,
        frozenset(("B", "C")): 0.1,
        frozenset(("A", "C")): 0.2,
    }
    assert complete_linkage_clusters(("C", "B", "A"), distances) == (
        ("A", "B"),
        ("C",),
    )
    assert complete_linkage_clusters(
        ("A", "B"),
        {frozenset(("A", "B")): None},
    ) == (("A",), ("B",))


def test_three_subfolds_need_sixty_and_direction_is_strictly_positive() -> None:
    enough = summarize_subfold_rankic("s1", (0.01,) * 60, 60)
    short = summarize_subfold_rankic("s2", (0.01,) * 59, 60)
    zero = summarize_subfold_rankic("s3", (0.0,) * 60, 60)
    assert enough.sample_sufficient
    assert not short.sample_sufficient
    assert not subfold_direction_consistent((enough, enough, zero))
    positive = CoreSubfoldRankICEvidence(
        subfold_id="positive",
        valid_count=60,
        signed_mean_rank_ic=1e-15,
        sample_sufficient=True,
    )
    assert subfold_direction_consistent((enough, enough, positive))
