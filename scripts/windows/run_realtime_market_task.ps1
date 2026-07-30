param(
    [Parameter(Mandatory = $true)][string]$Distro,
    [Parameter(Mandatory = $true)][string]$Workdir,
    [Parameter(Mandatory = $true)][string]$Command
)

$ErrorActionPreference = "Stop"
$LogRoot = Join-Path $env:LOCALAPPDATA "AstraMindOSMini"
$LogPath = Join-Path $LogRoot "realtime-task.log"
$MaxBytes = 2MB
$Generations = 4
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Rotate-Log {
    if (-not (Test-Path $LogPath) -or (Get-Item $LogPath).Length -lt $MaxBytes) { return }
    Remove-Item "$LogPath.$Generations" -ErrorAction SilentlyContinue
    for ($Index = $Generations - 1; $Index -ge 1; $Index--) {
        if (Test-Path "$LogPath.$Index") {
            Move-Item -Force "$LogPath.$Index" "$LogPath.$($Index + 1)"
        }
    }
    Move-Item -Force $LogPath "$LogPath.1"
}

function Redact-Line([string]$Value) {
    $Pattern = '(?i)(token|api[_ -]?key|secret|password|account(?:_id)?)\s*[:= ]\s*["'']?[^"'',;\s]+'
    return [regex]::Replace($Value, $Pattern, '$1=<redacted>')
}

Rotate-Log
try {
    & wsl.exe -d $Distro --cd $Workdir -- /bin/bash -lc $Command 2>&1 |
        ForEach-Object { Redact-Line ([string]$_) } |
        Tee-Object -FilePath $LogPath -Append
    $ExitCode = $LASTEXITCODE
} catch {
    Redact-Line "wsl_start_failed=$($_.Exception.GetType().Name)" |
        Out-File -FilePath $LogPath -Append -Encoding utf8
    exit 127
}
Redact-Line "wsl_exit_code=$ExitCode" | Out-File -FilePath $LogPath -Append -Encoding utf8
exit $ExitCode
