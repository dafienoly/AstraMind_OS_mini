"""Generate or verify deterministic JSON Schema for public contracts."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from astramind_mini.contracts import PUBLIC_CONTRACTS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "contracts/schema"


def rendered_schemas() -> dict[Path, str]:
    return {
        SCHEMA_DIR / f"{model.__name__}.schema.json": (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        )
        for model in PUBLIC_CONTRACTS
    }


def check() -> int:
    failures: list[str] = []
    expected = rendered_schemas()
    actual_files = set(SCHEMA_DIR.glob("*.schema.json")) if SCHEMA_DIR.exists() else set()
    for path, content in expected.items():
        if not path.exists():
            failures.append(f"缺少 {path.relative_to(ROOT)}")
        elif path.read_text(encoding="utf-8") != content:
            failures.append(f"漂移 {path.relative_to(ROOT)}")
    for extra in actual_files - set(expected):
        failures.append(f"多余 {extra.relative_to(ROOT)}")
    if failures:
        print("\n".join(failures))
        print("运行 make contracts-generate 更新生成物。")
        return 1
    print(f"公共契约 Schema：{len(expected)} 个，通过")
    return 0


def generate() -> int:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in rendered_schemas().items():
        path.write_text(content, encoding="utf-8")
    print(f"已生成 {len(PUBLIC_CONTRACTS)} 个公共契约 Schema。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    return check() if args.check else generate()


if __name__ == "__main__":
    sys.exit(main())
