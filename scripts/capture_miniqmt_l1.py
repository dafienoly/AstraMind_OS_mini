"""Explicit MiniQMT L1 capture command; market data only."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters.miniqmt_l1 import MiniQMTL1Capture
from astramind_mini.data.adapters.miniqmt_probe import ProbeRunnerError
from astramind_mini.data.adapters.realtime_store import RealtimeMicroBatchStore

ROOT = Path(__file__).resolve().parents[1]


async def run(seconds: float) -> int:
    settings = Settings()
    capture = MiniQMTL1Capture(
        runner=ROOT / "scripts/windows/miniqmt_l1_capture.py",
        python_command=settings.miniqmt_python,
        xtquant_path=settings.miniqmt_xtquant_path,
        quote_port=settings.miniqmt_quote_port,
        timeout_seconds=max(settings.miniqmt_probe_timeout_seconds, seconds + 10),
    )
    try:
        report, observations, raw_messages = await capture.capture(seconds=seconds)
    except ProbeRunnerError as error:
        print(f"MiniQMT L1 采集失败（脱敏错误码）：{error.code}")
        print("恢复：设置 ASTRAMIND_MINIQMT_XTQUANT_PATH 与 ASTRAMIND_MINIQMT_QUOTE_PORT 后重试")
        return 2
    batch, path = RealtimeMicroBatchStore(settings.data_dir).append(
        report, raw_messages, observations
    )
    print(
        f"MiniQMT L1 session={report.state.value} messages={report.received_messages} "
        f"quotes={batch.row_count} unsubscribed=true"
    )
    print(f"不可变证据：{path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=5)
    args = parser.parse_args()
    if not 0.5 <= args.seconds <= 60:
        parser.error("--seconds 必须在 0.5 到 60 之间")
    return asyncio.run(run(args.seconds))


if __name__ == "__main__":
    raise SystemExit(main())
