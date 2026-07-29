"""Apply already-frozen supported market-model challengers to read-only pointers."""

from __future__ import annotations

import argparse
import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from astramind_mini.config import Settings
from astramind_mini.strategy_research.public import (
    MarketModelCandidate,
    MarketModelEvidenceBundle,
    MarketModelManifest,
    MonthlyMarketModelActivationService,
    SkopsArtifactStore,
)


def run(args: argparse.Namespace) -> int:
    settings = Settings()
    root = settings.market_model_dir
    candidates = _candidates(args.candidate_dir)
    artifacts = SkopsArtifactStore(root)
    results = MonthlyMarketModelActivationService(
        root=root,
        artifact_validator=artifacts.load,
    ).reconcile(
        candidates,
        effective_at=args.effective_at or datetime.now(ZoneInfo("Asia/Shanghai")),
    )
    for result in results:
        print(f"{result.model_family}_state={result.state}")
        print(f"{result.model_family}_activation_id={result.activation_id}")
        if result.reason_codes:
            print(f"{result.model_family}_reasons={','.join(result.reason_codes)}")
    print("strategy_promotion_allowed=false")
    print("portfolio_targets_allowed=false")
    print("order_plans_allowed=false")
    print("broker_actions_allowed=false")
    return 0


def _candidates(directory: Path) -> tuple[MarketModelCandidate, ...]:
    candidates = []
    for manifest_path in sorted(directory.glob("*.manifest.json")):
        family = manifest_path.name.removesuffix(".manifest.json")
        evidence_path = directory / f"{family}.evidence.json"
        if not evidence_path.is_file():
            raise FileNotFoundError(f"候选缺少证据文件：{evidence_path}")
        candidates.append(
            MarketModelCandidate(
                manifest=MarketModelManifest.model_validate_json(
                    manifest_path.read_text(encoding="utf-8")
                ),
                evidence=MarketModelEvidenceBundle.model_validate_json(
                    evidence_path.read_text(encoding="utf-8")
                ),
            )
        )
    if not candidates:
        raise ValueError("候选目录没有 *.manifest.json")
    return tuple(candidates)


@contextmanager
def activation_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("市场模型月度激活已有进程在运行") from error
        yield


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--effective-at", type=datetime.fromisoformat)
    args = parser.parse_args()
    with activation_lock(Path("var/control/market-model-monthly-activation.lock")):
        return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
