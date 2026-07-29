param(
    [Parameter(Mandatory = $true)]
    [string]$TaskXml
)

$ErrorActionPreference = "Stop"
$taskName = "AstraMind OS Mini - Realtime Market"
$arguments = '/Create /TN "' + $taskName + '" /XML "' + $TaskXml + '" /F'
$process = Start-Process `
    -FilePath "$env:SystemRoot\System32\schtasks.exe" `
    -ArgumentList $arguments `
    -Verb RunAs `
    -Wait `
    -PassThru
exit $process.ExitCode
