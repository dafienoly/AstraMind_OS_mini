from pathlib import Path

from scripts.check_architecture import find_violations


def test_cross_context_internal_import_fails_but_public_import_passes(
    tmp_path: Path,
) -> None:
    source = tmp_path / "astramind_mini"
    module = source / "data/example.py"
    module.parent.mkdir(parents=True)
    module.write_text(
        "from astramind_mini.strategy_research.domain import hidden\n"
        "from astramind_mini.strategy_research.public import StrategyVersion\n",
        encoding="utf-8",
    )

    violations = find_violations(source)

    assert len(violations) == 1
    assert "strategy_research.domain" in violations[0]
