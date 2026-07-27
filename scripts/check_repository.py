"""Repository hygiene checks that do not depend on external binaries."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
LINK_PATTERN = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")
SECRET_PATTERN = re.compile(r"(?i)(?:token|password|secret|account_id)\s*[:=]\s*[\"']?([^\s\"'#]+)")
EXCLUDED_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "playwright-report",
    "test-results",
}
REQUIREMENT_FILE_PATTERN = re.compile(r"^REQ-(\d{4})-(\d{4})-.+\.md$")


def repository_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / item for item in result.stdout.splitlines() if item]


def check_markdown_links(files: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in (item for item in files if item.suffix.lower() == ".md"):
        text = path.read_text(encoding="utf-8")
        for raw_target in LINK_PATTERN.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if (
                not target
                or target.startswith(("#", "http://", "https://", "mailto:"))
                or "://" in target
            ):
                continue
            relative = unquote(target.split("#", 1)[0])
            resolved = (path.parent / relative).resolve()
            if not resolved.exists():
                failures.append(f"{path.relative_to(ROOT)}: 本地链接不存在：{target}")
    return failures


def check_svg(files: list[Path]) -> list[str]:
    failures: list[str] = []
    for path in (item for item in files if item.suffix.lower() == ".svg"):
        try:
            ET.parse(path)
        except ET.ParseError as error:
            failures.append(f"{path.relative_to(ROOT)}: SVG 无法解析：{error}")
    return failures


def check_doc_language(files: list[Path]) -> list[str]:
    allowed_english = {
        Path("AGENTS.md"),
        Path("CONTEXT-MAP.md"),
        Path("docs/development/vibe-coding.md"),
        Path("docs/development/work-package-template.md"),
    }
    failures: list[str] = []
    for path in (item for item in files if item.suffix.lower() == ".md"):
        relative = path.relative_to(ROOT)
        if relative in allowed_english or relative.match("docs/contexts/*/CONTEXT.md"):
            continue
        if not re.search(r"[\u4e00-\u9fff]", path.read_text(encoding="utf-8")):
            failures.append(f"{relative}: 面向用户文档缺少中文正文")
    return failures


def check_proposal_approvals(files: list[Path]) -> list[str]:
    failures: list[str] = []
    proposals = [
        item
        for item in files
        if item.name == "proposal.md" and "docs/ui/proposals" in item.as_posix()
    ]
    for path in proposals:
        text = path.read_text(encoding="utf-8")
        version_match = re.search(r"^approved_version:[ \t]*(\S+)?[ \t]*$", text, re.MULTILINE)
        if version_match and version_match.group(1):
            if not re.search(r"^approved_by:\s*user\s*$", text, re.MULTILINE):
                failures.append(f"{path.relative_to(ROOT)}: 已批准版本缺少 approved_by: user")
            if not re.search(r"^approved_at:\s*\d{4}-\d{2}-\d{2}\s*$", text, re.MULTILINE):
                failures.append(f"{path.relative_to(ROOT)}: 已批准版本缺少批准日期")
    return failures


def check_requirement_sequence(files: list[Path]) -> list[str]:
    failures: list[str] = []
    by_year: dict[str, list[tuple[int, Path]]] = {}
    for path in files:
        if path.parent != ROOT / "docs/requirements":
            continue
        match = REQUIREMENT_FILE_PATTERN.match(path.name)
        if not match:
            continue
        year, number = match.groups()
        by_year.setdefault(year, []).append((int(number), path))
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        expected_id = f"REQ-{year}-{number}"
        if expected_id not in first_line:
            failures.append(f"{path.name}: 标题需求编号应为 {expected_id}")

    for year, entries in by_year.items():
        numbers = sorted(number for number, _ in entries)
        expected = list(range(1, max(numbers, default=0) + 1))
        missing = sorted(set(expected) - set(numbers))
        duplicates = sorted(number for number in set(numbers) if numbers.count(number) > 1)
        if missing:
            failures.append(
                f"docs/requirements: {year} 年需求编号缺失 "
                + "、".join(f"{number:04d}" for number in missing)
            )
        if duplicates:
            failures.append(
                f"docs/requirements: {year} 年需求编号重复 "
                + "、".join(f"{number:04d}" for number in duplicates)
            )
    return failures


def check_secrets(files: list[Path]) -> list[str]:
    failures: list[str] = []
    risky_names = {".env", ".env.local", "id_rsa", "credentials.json"}
    text_suffixes = {".py", ".ts", ".tsx", ".js", ".json", ".toml", ".yaml", ".yml"}
    for path in files:
        relative = path.relative_to(ROOT)
        if path.name in risky_names:
            failures.append(f"{relative}: 禁止纳入仓库的密钥文件名")
        if path.suffix.lower() not in text_suffixes or "docs" in relative.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in SECRET_PATTERN.finditer(text):
            value = match.group(1)
            allowed_markers = {
                "none",
                "null",
                "undefined",
                "secretstr",
                "str",
            }
            lowered = value.lower()
            is_placeholder = any(
                marker in lowered for marker in ("placeholder", "example", "dummy", "test")
            )
            if lowered not in allowed_markers and not is_placeholder:
                failures.append(f"{relative}: 疑似硬编码密钥或账户标识")
                break
    return failures


def function_lengths(path: Path) -> list[tuple[str, int]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    lengths: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.end_lineno:
            lengths.append((node.name, node.end_lineno - node.lineno + 1))
    return lengths


def check_budgets(files: list[Path]) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    warnings: list[str] = []
    generated = Path("contracts/schema")
    for path in files:
        relative = path.relative_to(ROOT)
        if generated in relative.parents or any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        if path.suffix not in {".py", ".ts", ".tsx"}:
            continue
        lines = len(path.read_text(encoding="utf-8").splitlines())
        block = 350 if path.suffix == ".tsx" else 500
        warn = 250 if path.suffix == ".tsx" else 350
        if lines > block:
            failures.append(f"{relative}: {lines} 行，超过阻断阈值 {block}")
        elif lines > warn:
            warnings.append(f"{relative}: {lines} 行，超过警告阈值 {warn}")
        if path.suffix == ".py":
            for name, length in function_lengths(path):
                if length > 120:
                    failures.append(f"{relative}:{name}: {length} 行，超过函数阻断阈值 120")
                elif length > 80:
                    warnings.append(f"{relative}:{name}: {length} 行，超过函数警告阈值 80")
    return failures, warnings


def main() -> int:
    files = repository_files()
    failures = [
        *check_markdown_links(files),
        *check_svg(files),
        *check_doc_language(files),
        *check_proposal_approvals(files),
        *check_requirement_sequence(files),
        *check_secrets(files),
    ]
    budget_failures, warnings = check_budgets(files)
    failures.extend(budget_failures)
    for warning in warnings:
        print(f"警告：{warning}")
    if failures:
        print("\n".join(f"失败：{failure}" for failure in failures))
        return 1
    print(f"仓库检查：{len(files)} 个文件，本地链接、SVG、批准记录、密钥和规模均通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
