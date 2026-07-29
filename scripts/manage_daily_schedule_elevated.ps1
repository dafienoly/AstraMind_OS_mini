param(
    [Parameter(Mandatory = $true)]
    [string]$TaskXml,
    [ValidateSet("Install", "Run")]
    [string]$Mode = "Install"
)

$ErrorActionPreference = "Stop"
$taskName = "AstraMind OS Mini - Daily Ops"
$arguments = if ($Mode -eq "Run") {
    '/Run /TN "' + $taskName + '"'
} else {
    '/Create /TN "' + $taskName + '" /XML "' + $TaskXml + '" /F'
}
$process = Start-Process `
    -FilePath "$env:SystemRoot\System32\schtasks.exe" `
    -ArgumentList $arguments `
    -Verb RunAs `
    -Wait `
    -PassThru
exit $process.ExitCode
