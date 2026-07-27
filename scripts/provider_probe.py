"""Explicit, read-only Tushare and MiniQMT capability probe command."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from astramind_mini.config import Settings
from astramind_mini.data.adapters import DataControlLedger, FilesystemRawRecordStore
from astramind_mini.data.adapters.miniqmt_probe import MiniQMTCapabilityProbe
from astramind_mini.data.adapters.provider_config import load_tushare_probe_config
from astramind_mini.data.adapters.tushare_probe import TushareCapabilityProbe
from astramind_mini.data.application import canonical_json
from astramind_mini.data.contracts import CapabilityState, ProbeReport

ROOT = Path(__file__).resolve().parents[1]


async def run(provider_env_file: Path) -> int:
    settings = Settings()
    tushare_config = load_tushare_probe_config(settings, provider_env_file)
    probes = (
        TushareCapabilityProbe(tushare_config),
        MiniQMTCapabilityProbe(
            runner=ROOT / "scripts/windows/miniqmt_readonly_probe.py",
            python_command=settings.miniqmt_python,
            xtquant_path=settings.miniqmt_xtquant_path,
            quote_port=settings.miniqmt_quote_port,
            timeout_seconds=settings.miniqmt_probe_timeout_seconds,
        ),
    )
    results = await asyncio.gather(*(probe.probe() for probe in probes))
    raw_store = FilesystemRawRecordStore(settings.data_dir)
    ledger = DataControlLedger(settings.control_db_path)
    ledger.migrate()
    reports: list[ProbeReport] = []
    for report, records in results:
        reports.append(report)
        for envelope, payload in records:
            raw_store.append(envelope, payload)
        path = _write_report(settings.data_dir, report)
        ledger.record_probe(report, path)
        _print_summary(report)
    return int(
        any(
            not any(
                capability.state is CapabilityState.AVAILABLE for capability in report.capabilities
            )
            for report in reports
        )
    )


def _write_report(root: Path, report: ProbeReport) -> Path:
    digest = report.probe_id.rsplit(":", 1)[-1]
    path = root / "provider-probes" / report.provider / digest / "report.json"
    payload = canonical_json(report.model_dump(mode="json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(payload)
    except FileExistsError:
        if path.read_bytes() != payload:
            raise RuntimeError("探测报告身份冲突") from None
    return path


def _print_summary(report: ProbeReport) -> None:
    print(f"{report.provider} client={report.client_version}")
    for capability in report.capabilities:
        print(
            f"  {capability.interface_name}: {capability.state.value} rows={capability.row_count}"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider-env-file", type=Path, required=True)
    args = parser.parse_args()
    return asyncio.run(run(args.provider_env_file))


if __name__ == "__main__":
    raise SystemExit(main())
