"""Fail-closed installation of the Windows-local realtime task wrapper."""

from __future__ import annotations

import subprocess
from pathlib import Path

from astramind_mini.local_ops.realtime_service_deployment import RealtimeMarketTaskSpec

_ATOMIC_INSTALL_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$Source = $args[0]
$Target = $args[1]
$Directory = Split-Path -Parent $Target
New-Item -ItemType Directory -Force -Path $Directory | Out-Null
$Temporary = "$Target.tmp-$PID"
try {
    Copy-Item -LiteralPath $Source -Destination $Temporary -Force
    $SourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Source).Hash
    $TemporaryHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Temporary).Hash
    if ($SourceHash -ne $TemporaryHash) { throw 'wrapper temporary hash mismatch' }
    Move-Item -LiteralPath $Temporary -Destination $Target -Force
    $TargetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $Target).Hash
    if ($SourceHash -ne $TargetHash) { throw 'wrapper installed hash mismatch' }
    Write-Output "wrapper_hash=$TargetHash"
} finally {
    Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
}
"""


def windows_local_app_data() -> str:
    command = "[Environment]::GetFolderPath('LocalApplicationData')"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        check=True,
        capture_output=True,
        text=True,
    )
    value = completed.stdout.strip()
    if len(value) < 3 or value[1:3] not in {":\\", ":/"}:
        raise ValueError("无法确认 Windows 当前用户 LOCALAPPDATA")
    return value


def install_windows_wrapper(
    spec: RealtimeMarketTaskSpec,
) -> subprocess.CompletedProcess[str]:
    source = Path("scripts/windows/run_realtime_market_task.ps1")
    try:
        return subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                _ATOMIC_INSTALL_SCRIPT,
                _windows_path(source),
                spec.wrapper_path,
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as error:
        return subprocess.CompletedProcess(
            ["powershell.exe", "-Command", "<wrapper-install>"],
            127,
            "",
            f"wrapper_install_start_failed:{type(error).__name__}",
        )


def _windows_path(path: Path) -> str:
    completed = subprocess.run(
        ["wslpath", "-w", str(path.resolve())],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


__all__ = ["install_windows_wrapper", "windows_local_app_data"]
