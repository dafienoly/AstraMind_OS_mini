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
$MaxLineCharacters = 131072
$Utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

function Limit-LogFile([string]$Path) {
    if (-not (Test-Path $Path) -or (Get-Item $Path).Length -le $MaxBytes) { return }
    $Bytes = [System.IO.File]::ReadAllBytes($Path)
    $Tail = New-Object byte[] $MaxBytes
    [Array]::Copy($Bytes, $Bytes.Length - $MaxBytes, $Tail, 0, $MaxBytes)
    [System.IO.File]::WriteAllBytes($Path, $Tail)
}

function Rotate-Log([long]$IncomingBytes) {
    for ($Generation = 1; $Generation -le $Generations; $Generation++) {
        Limit-LogFile "$LogPath.$Generation"
    }
    Limit-LogFile $LogPath
    if (-not (Test-Path $LogPath)) { return }
    if ((Get-Item $LogPath).Length + $IncomingBytes -le $MaxBytes) { return }
    Remove-Item "$LogPath.$Generations" -ErrorAction SilentlyContinue
    for ($Index = $Generations - 1; $Index -ge 1; $Index--) {
        if (Test-Path "$LogPath.$Index") {
            Move-Item -Force "$LogPath.$Index" "$LogPath.$($Index + 1)"
        }
    }
    Move-Item -Force $LogPath "$LogPath.1"
}

function Redact-Line([string]$Value) {
    $Pattern = @'
(?ix)(?<![a-z0-9_\\/])(?<prefix>["']?(?:token|api[_ -]?key|secret|password|account(?:_id)?)["']?\s*(?::|=|\s)\s*)(?:"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^,;\r\n]*)
'@
    return [regex]::Replace(
        $Value,
        $Pattern,
        { param($Match) "$($Match.Groups['prefix'].Value)<redacted>" }
    )
}

function Write-BoundedLog([string]$Value) {
    $SafeValue = Redact-Line $Value
    if ($SafeValue.Length -gt $MaxLineCharacters) {
        $SafeValue = $SafeValue.Substring(0, $MaxLineCharacters) + "<truncated>"
    }
    $Payload = "$SafeValue`r`n"
    $PayloadBytes = $Utf8.GetByteCount($Payload)
    Rotate-Log $PayloadBytes
    [System.IO.File]::AppendAllText($LogPath, $Payload, $Utf8)
    Limit-LogFile $LogPath
    Rotate-Log 0
}

Rotate-Log 0
try {
    & wsl.exe -d $Distro --cd $Workdir -- /bin/bash -lc $Command 2>&1 |
        ForEach-Object {
            $Line = Redact-Line ([string]$_)
            Write-Output $Line
            Write-BoundedLog $Line
        }
    $ExitCode = $LASTEXITCODE
} catch {
    Write-BoundedLog "wsl_start_failed=$($_.Exception.GetType().Name)"
    exit 127
}
Write-BoundedLog "wsl_exit_code=$ExitCode"
exit $ExitCode
