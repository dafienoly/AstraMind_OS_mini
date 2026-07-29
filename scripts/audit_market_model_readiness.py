"""Report production-data blockers without training or activating a model."""

from __future__ import annotations

from astramind_mini.config import Settings
from astramind_mini.strategy_research.adapters import MarketModelReadinessReader


def main() -> int:
    report = MarketModelReadinessReader(Settings().data_dir).current()
    print(f"data_snapshot_id={report.data_snapshot_id}")
    print(f"as_of={report.as_of}")
    for item in report.models:
        print(f"{item.model_family}_development_ready={str(item.development_ready).lower()}")
        print(
            f"{item.model_family}_supportive_evidence_ready="
            f"{str(item.supportive_evidence_ready).lower()}"
        )
        if item.reason_codes:
            print(f"{item.model_family}_reasons={','.join(item.reason_codes)}")
    print("broker_actions_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
