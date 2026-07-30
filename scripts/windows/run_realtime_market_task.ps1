param(
    [Parameter(Mandatory = $true)][string]$Distro,
    [Parameter(Mandatory = $true)][string]$Workdir,
    [Parameter(Mandatory = $true)]
    [ValidateSet("realtime-market-service-run")]
    [string]$MakeTarget
)

$ErrorActionPreference = "Stop"
$LogRoot = Join-Path $env:LOCALAPPDATA "AstraMindOSMini"
$LogPath = Join-Path $LogRoot "realtime-task.log"
$StatusPath = Join-Path $LogRoot "realtime-task-status.json"
$MaxBytes = 2MB
$Generations = 4
$MaxLineCharacters = 131072
$MaxCaptureCharacters = 524288
$Utf8 = New-Object System.Text.UTF8Encoding($false)
New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

$NativeProcessSource = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace AstraMind.Realtime
{
    public sealed class CaptureResult
    {
        public string Text { get; set; }
        public long CharactersSeen { get; set; }
        public bool Truncated { get; set; }
        public int DroppedLines { get; set; }
        public int TruncatedLines { get; set; }
    }

    public sealed class NativeProcessResult
    {
        public int ExitCode { get; set; }
        public CaptureResult StandardOutput { get; set; }
        public CaptureResult StandardError { get; set; }
    }

    public static class NativeProcessRunner
    {
        public static NativeProcessResult Run(
            string executable,
            string[] arguments,
            int maxCaptureCharacters,
            int maxLineCharacters)
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = executable;
            startInfo.Arguments = BuildArguments(arguments);
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            startInfo.RedirectStandardOutput = true;
            startInfo.RedirectStandardError = true;
            startInfo.StandardOutputEncoding = new UTF8Encoding(false, false);
            startInfo.StandardErrorEncoding = new UTF8Encoding(false, false);

            using (Process process = new Process())
            {
                process.StartInfo = startInfo;
                if (!process.Start())
                {
                    throw new InvalidOperationException("native process did not start");
                }
                Task<CaptureResult> stdout = StartCapture(
                    process.StandardOutput,
                    maxCaptureCharacters,
                    maxLineCharacters);
                Task<CaptureResult> stderr = StartCapture(
                    process.StandardError,
                    maxCaptureCharacters,
                    maxLineCharacters);
                process.WaitForExit();
                Task.WaitAll(stdout, stderr);
                return new NativeProcessResult
                {
                    ExitCode = process.ExitCode,
                    StandardOutput = stdout.Result,
                    StandardError = stderr.Result
                };
            }
        }

        public static string BuildArguments(string[] arguments)
        {
            if (arguments == null)
            {
                throw new ArgumentNullException("arguments");
            }
            StringBuilder commandLine = new StringBuilder();
            for (int index = 0; index < arguments.Length; index++)
            {
                if (index > 0)
                {
                    commandLine.Append(' ');
                }
                commandLine.Append(QuoteArgument(arguments[index]));
            }
            return commandLine.ToString();
        }

        private static string QuoteArgument(string value)
        {
            if (value == null)
            {
                throw new ArgumentNullException("value");
            }
            if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
            {
                return value;
            }
            StringBuilder quoted = new StringBuilder();
            quoted.Append('"');
            int backslashes = 0;
            foreach (char character in value)
            {
                if (character == '\\')
                {
                    backslashes++;
                    continue;
                }
                if (character == '"')
                {
                    quoted.Append('\\', (backslashes * 2) + 1);
                    quoted.Append('"');
                    backslashes = 0;
                    continue;
                }
                quoted.Append('\\', backslashes);
                quoted.Append(character);
                backslashes = 0;
            }
            quoted.Append('\\', backslashes * 2);
            quoted.Append('"');
            return quoted.ToString();
        }

        private static Task<CaptureResult> StartCapture(
            TextReader reader,
            int maxCaptureCharacters,
            int maxLineCharacters)
        {
            return Task.Factory.StartNew(
                delegate { return Capture(reader, maxCaptureCharacters, maxLineCharacters); },
                CancellationToken.None,
                TaskCreationOptions.LongRunning,
                TaskScheduler.Default);
        }

        private static CaptureResult Capture(
            TextReader reader,
            int maxCaptureCharacters,
            int maxLineCharacters)
        {
            Queue<string> lines = new Queue<string>();
            StringBuilder current = new StringBuilder();
            char[] buffer = new char[4096];
            long charactersSeen = 0;
            int retainedCharacters = 0;
            int droppedLines = 0;
            int truncatedLines = 0;
            bool lineTruncated = false;
            bool previousWasCarriageReturn = false;
            int count;
            while ((count = reader.Read(buffer, 0, buffer.Length)) > 0)
            {
                for (int index = 0; index < count; index++)
                {
                    char character = buffer[index];
                    charactersSeen++;
                    if (character == '\r' || character == '\n')
                    {
                        if (!(character == '\n' && previousWasCarriageReturn))
                        {
                            CommitLine(
                                lines,
                                current,
                                lineTruncated,
                                maxCaptureCharacters,
                                ref retainedCharacters,
                                ref droppedLines,
                                ref truncatedLines);
                            current.Clear();
                            lineTruncated = false;
                        }
                        previousWasCarriageReturn = character == '\r';
                        continue;
                    }
                    previousWasCarriageReturn = false;
                    if (current.Length < maxLineCharacters)
                    {
                        current.Append(character);
                    }
                    else
                    {
                        lineTruncated = true;
                    }
                }
            }
            if (current.Length > 0 || lineTruncated)
            {
                CommitLine(
                    lines,
                    current,
                    lineTruncated,
                    maxCaptureCharacters,
                    ref retainedCharacters,
                    ref droppedLines,
                    ref truncatedLines);
            }
            return new CaptureResult
            {
                Text = String.Join(Environment.NewLine, lines.ToArray()),
                CharactersSeen = charactersSeen,
                Truncated = droppedLines > 0 || truncatedLines > 0,
                DroppedLines = droppedLines,
                TruncatedLines = truncatedLines
            };
        }

        private static void CommitLine(
            Queue<string> lines,
            StringBuilder current,
            bool lineTruncated,
            int maxCaptureCharacters,
            ref int retainedCharacters,
            ref int droppedLines,
            ref int truncatedLines)
        {
            string line = current.ToString();
            if (lineTruncated)
            {
                line += "<truncated-line>";
                truncatedLines++;
            }
            while (lines.Count > 0 &&
                retainedCharacters + line.Length + Environment.NewLine.Length >
                    maxCaptureCharacters)
            {
                string removed = lines.Dequeue();
                retainedCharacters -= removed.Length + Environment.NewLine.Length;
                droppedLines++;
            }
            if (line.Length <= maxCaptureCharacters)
            {
                lines.Enqueue(line);
                retainedCharacters += line.Length + Environment.NewLine.Length;
            }
            else
            {
                droppedLines++;
            }
        }
    }
}
'@

function Initialize-NativeProcessRunner {
    if ($null -eq ("AstraMind.Realtime.NativeProcessRunner" -as [type])) {
        Add-Type -TypeDefinition $NativeProcessSource -Language CSharp
    }
}

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

function Limit-DiagnosticText([string]$Value, [int]$Limit = 2048) {
    $SafeValue = Redact-Line $Value
    if ($SafeValue.Length -le $Limit) { return $SafeValue }
    return $SafeValue.Substring(0, $Limit) + "<truncated>"
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

function Write-CapturedOutput([string]$StreamName, [string]$Value) {
    if ([string]::IsNullOrEmpty($Value)) { return }
    foreach ($Line in [regex]::Split($Value, "\r\n|\n|\r")) {
        $SafeLine = Redact-Line ([string]$Line)
        Write-Output $SafeLine
        Write-BoundedLog "$StreamName=$SafeLine"
    }
}

function Write-WrapperStatus([string]$State, [hashtable]$Evidence) {
    $Record = [ordered]@{
        schema_version = 2
        state = $State
        updated_at = [DateTimeOffset]::UtcNow.ToString("o")
        wsl_executable = $null
        native_exit_code = $null
        exception_type = $null
        exception_message = $null
        exception_hresult = $null
        stdout_characters_seen = 0
        stderr_characters_seen = 0
        stdout_truncated = $false
        stderr_truncated = $false
        log_path = $LogPath
    }
    foreach ($Key in $Evidence.Keys) {
        $Record[$Key] = $Evidence[$Key]
    }
    $Temporary = "$StatusPath.tmp-$PID-$([guid]::NewGuid().ToString('N'))"
    $Backup = "$StatusPath.bak-$PID"
    try {
        $Payload = $Record | ConvertTo-Json -Compress
        [System.IO.File]::WriteAllText($Temporary, $Payload, $Utf8)
        if (Test-Path -LiteralPath $StatusPath) {
            [System.IO.File]::Replace($Temporary, $StatusPath, $Backup, $true)
        } else {
            [System.IO.File]::Move($Temporary, $StatusPath)
        }
    } finally {
        Remove-Item -LiteralPath $Temporary -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $Backup -Force -ErrorAction SilentlyContinue
    }
}

function Get-DiagnosticException([Exception]$Exception) {
    $Current = $Exception
    for ($Depth = 0; $Depth -lt 4 -and $null -ne $Current.InnerException; $Depth++) {
        $Current = $Current.InnerException
    }
    return $Current
}

function Get-WslExecutablePath {
    return Join-Path $env:SystemRoot "System32\wsl.exe"
}

function Invoke-RealtimeMarketTask {
    $WslPath = Get-WslExecutablePath
    $NativeArguments = @(
        "-d",
        $Distro,
        "--cd",
        $Workdir,
        "--",
        "/usr/bin/uv",
        "run",
        "python",
        "scripts/manage_realtime_market_service.py",
        "run-task",
        "--make-target",
        $MakeTarget
    )
    Rotate-Log 0
    try {
        Write-WrapperStatus "running" @{wsl_executable = $WslPath}
        Initialize-NativeProcessRunner
        if (-not [System.IO.File]::Exists($WslPath)) {
            throw New-Object System.IO.FileNotFoundException(
                "absolute wsl executable is unavailable",
                $WslPath
            )
        }
        $Result = [AstraMind.Realtime.NativeProcessRunner]::Run(
            $WslPath,
            [string[]]$NativeArguments,
            $MaxCaptureCharacters,
            $MaxLineCharacters
        )
        Write-CapturedOutput "wsl_stdout" $Result.StandardOutput.Text
        Write-CapturedOutput "wsl_stderr" $Result.StandardError.Text
        if ($Result.StandardOutput.Truncated) {
            Write-BoundedLog (
                "wsl_stdout_truncated=true characters_seen=" +
                $Result.StandardOutput.CharactersSeen
            )
        }
        if ($Result.StandardError.Truncated) {
            Write-BoundedLog (
                "wsl_stderr_truncated=true characters_seen=" +
                $Result.StandardError.CharactersSeen
            )
        }
        $Evidence = @{
            wsl_executable = $WslPath
            native_exit_code = $Result.ExitCode
            stdout_characters_seen = $Result.StandardOutput.CharactersSeen
            stderr_characters_seen = $Result.StandardError.CharactersSeen
            stdout_truncated = $Result.StandardOutput.Truncated
            stderr_truncated = $Result.StandardError.Truncated
        }
        if ($Result.ExitCode -ne 0) {
            Write-WrapperStatus "wsl_native_exit" $Evidence
            Write-BoundedLog "wsl_native_exit_code=$($Result.ExitCode)"
        } else {
            Write-WrapperStatus "completed" $Evidence
            Write-BoundedLog "wsl_exit_code=0"
        }
        exit $Result.ExitCode
    } catch {
        $Exception = Get-DiagnosticException $_.Exception
        $ExceptionType = $Exception.GetType().FullName
        $ExceptionMessage = Limit-DiagnosticText $Exception.Message
        $ExceptionHResult = "0x$($Exception.HResult.ToString('X8'))"
        Write-BoundedLog (
            "wrapper_launch_exception wsl_path=$WslPath type=$ExceptionType " +
            "hresult=$ExceptionHResult message=$ExceptionMessage"
        )
        try {
            Write-WrapperStatus "wrapper_launch_exception" @{
                wsl_executable = $WslPath
                native_exit_code = 127
                exception_type = $ExceptionType
                exception_message = $ExceptionMessage
                exception_hresult = $ExceptionHResult
            }
        } catch {
            Write-BoundedLog "wrapper_status_write_failed=$($_.Exception.GetType().FullName)"
        }
        exit 127
    }
}

if ($MyInvocation.InvocationName -ne ".") {
    Invoke-RealtimeMarketTask
}
