from pathlib import Path

import pytest

import scripts.check_repository as repository_check


def requirement(path: Path, identifier: str) -> Path:
    path.write_text(f"# {identifier}：测试需求\n", encoding="utf-8")
    return path


def test_requirement_sequence_detects_gap_and_title_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requirements = tmp_path / "docs/requirements"
    requirements.mkdir(parents=True)
    files = [
        requirement(requirements / "REQ-2026-0001-first.md", "REQ-2026-0001"),
        requirement(requirements / "REQ-2026-0003-third.md", "REQ-2026-9999"),
    ]
    monkeypatch.setattr(repository_check, "ROOT", tmp_path)

    failures = repository_check.check_requirement_sequence(files)

    assert any("缺失 0002" in failure for failure in failures)
    assert any("标题需求编号应为 REQ-2026-0003" in failure for failure in failures)
