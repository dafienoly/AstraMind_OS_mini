"""Enforce public-only imports between bounded contexts."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/astramind_mini"
CONTEXTS = {
    "data",
    "market_regime",
    "strategy_research",
    "portfolio_risk",
    "trading_execution",
}


def module_context(path: Path, source: Path = SOURCE) -> str | None:
    try:
        first = path.relative_to(source).parts[0]
    except ValueError:
        return None
    return first if first in CONTEXTS else None


def imported_context(module: str) -> tuple[str, tuple[str, ...]] | None:
    parts = tuple(module.split("."))
    if len(parts) < 2 or parts[0] != "astramind_mini" or parts[1] not in CONTEXTS:
        return None
    return parts[1], parts[2:]


def is_public_import(tail: tuple[str, ...]) -> bool:
    return not tail or tail[0] == "public"


def find_violations(source: Path = SOURCE) -> list[str]:
    violations: list[str] = []
    for path in source.rglob("*.py"):
        owner = module_context(path, source)
        if owner is None:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.append(node.module)
            for module in modules:
                imported = imported_context(module)
                if imported is None:
                    continue
                target, tail = imported
                if target != owner and not is_public_import(tail):
                    location = f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', 0)}"
                    violations.append(f"{location} 禁止跨上下文导入 {module}")
    return violations


def main() -> int:
    violations = find_violations()
    if violations:
        print("\n".join(violations))
        return 1
    print("上下文依赖检查：通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
