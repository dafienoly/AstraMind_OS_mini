import re
from pathlib import Path

import pytest

import scripts.check_repository as repository_check

ROOT = Path(__file__).resolve().parents[2]
REQUIREMENT_REFERENCE = re.compile(r"^- 需求：(.+)$", re.MULTILINE)
VERSIONED_REQUIREMENT = re.compile(r"REQ-2026-\d{4} v\d+\.\d+\.\d+")
REQUIREMENT_VERSION = re.compile(r"^- 需求版本：(\d+\.\d+\.\d+)$", re.MULTILINE)


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


def test_every_work_package_has_a_versioned_requirement_and_trace_row() -> None:
    traceability = (ROOT / "docs/requirements/README.md").read_text(encoding="utf-8")
    work_packages = sorted((ROOT / "docs/planning/work-packages").glob("WP-*.md"))

    for path in work_packages:
        content = path.read_text(encoding="utf-8")
        reference = REQUIREMENT_REFERENCE.search(content)
        assert reference, f"{path.name} 缺少需求元数据"
        assert VERSIONED_REQUIREMENT.search(reference.group(1)), f"{path.name} 未引用带版本的 REQ"
        match = re.match(r"^(WP-\d{4}[A-Z]?(?:-H\d+)?)", path.name)
        assert match is not None, f"{path.name} 的 WP 编号无法识别"
        work_package_id = match.group(1)
        assert work_package_id in traceability, f"{work_package_id} 未进入唯一追踪表"


def test_every_requirement_has_exactly_one_authoritative_trace_row() -> None:
    traceability = (ROOT / "docs/requirements/README.md").read_text(encoding="utf-8")
    requirements = sorted((ROOT / "docs/requirements").glob("REQ-*.md"))

    assert traceability.count("## 唯一追踪表") == 1
    assert traceability.count("| REQ | 版本与状态 |") == 1

    for path in requirements:
        match = re.match(r"^(REQ-2026-\d{4})", path.name)
        assert match is not None, f"{path.name} 的 REQ 编号无法识别"
        identifier = match.group(1)
        content = path.read_text(encoding="utf-8")
        version = REQUIREMENT_VERSION.search(content)
        assert version is not None, f"{path.name} 缺少需求版本"
        assert traceability.count(f"[{identifier}：") == 1, (
            f"{identifier} 必须且只能有一条权威追踪记录"
        )
        assert f"| {version.group(1)}；" in traceability, f"{identifier} 的追踪版本与正文不一致"
