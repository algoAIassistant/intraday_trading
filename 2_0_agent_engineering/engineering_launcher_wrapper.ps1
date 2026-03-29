# engineering_launcher_wrapper.ps1
#
# Daily session wrapper for the intraday_same_day Alpaca paper trading track.
#
# Reads credentials from .claude/settings.local.json (repo root), sets them
# into the current process environment, then launches the Python daily launcher.
#
# Designed as the Task Scheduler entrypoint — no manual env-var setup needed.
#
# Usage (manual):
#   powershell -ExecutionPolicy Bypass -File engineering_launcher_wrapper.ps1
#
# Usage (Task Scheduler):
#   Configured automatically by engineering_install_scheduled_task.ps1
#
# Dry-run vs paper-order mode is controlled entirely by the YAML config:
#   alpaca_submit_orders: false  ->  dry-run (no orders sent)
#   alpaca_submit_orders: true   ->  live paper orders submitted to Alpaca Paper

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot   = Split-Path -Parent $ScriptDir   # one level up from 2_0_agent_engineering/

$SettingsPath = Join-Path $RepoRoot ".claude\settings.local.json"
$LauncherPath = Join-Path $RepoRoot "2_0_agent_engineering\engineering_daily_launcher_intraday_same_day.py"

$LogDir  = Join-Path $RepoRoot "2_0_agent_engineering\engineering_runtime_outputs\wrapper_logs"
$DateStr = (Get-Date).ToString("yyyy_MM_dd")
$LogFile = Join-Path $LogDir "wrapper_log__$DateStr.txt"

# ---------------------------------------------------------------------------
# Log helper — writes timestamped lines to both console and file
# ---------------------------------------------------------------------------
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $Line = "{0}  [{1}]  {2}" -f (Get-Date -Format "HH:mm:ss"), $Level, $Message
    Write-Host $Line
    $null = New-Item -ItemType Directory -Force -Path $LogDir
    Add-Content -Path $LogFile -Value $Line -Encoding UTF8
}

# ---------------------------------------------------------------------------
# Validate required files
# ---------------------------------------------------------------------------
if (-not (Test-Path $SettingsPath)) {
    Write-Log "Settings file not found: $SettingsPath" "ERROR"
    exit 1
}

if (-not (Test-Path $LauncherPath)) {
    Write-Log "Launcher not found: $LauncherPath" "ERROR"
    exit 1
}

# ---------------------------------------------------------------------------
# Load credentials from .claude/settings.local.json
# ---------------------------------------------------------------------------
Write-Log "Loading credentials from .claude/settings.local.json"

try {
    $Settings = Get-Content $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
} catch {
    Write-Log "Failed to parse settings file: $_" "ERROR"
    exit 1
}

$Required = @("ALPACA_API_KEY", "ALPACA_API_SECRET", "APCA_API_BASE_URL")

foreach ($Key in $Required) {
    $Val = $Settings.env."$Key"
    if ([string]::IsNullOrWhiteSpace($Val)) {
        Write-Log "Required key '$Key' is missing or empty in .claude/settings.local.json" "ERROR"
        exit 1
    }
    [System.Environment]::SetEnvironmentVariable($Key, $Val, "Process")
}

Write-Log "Credentials loaded (keys: $($Required -join ', '))"

# ---------------------------------------------------------------------------
# Locate Python
# ---------------------------------------------------------------------------
$PythonExe = $null

$PythonOnPath = Get-Command python -ErrorAction SilentlyContinue
if ($PythonOnPath) {
    $PythonExe = $PythonOnPath.Source
} else {
    $FallbackPath = "C:\Users\yambi\AppData\Local\Programs\Python\Python314\python.exe"
    if (Test-Path $FallbackPath) {
        $PythonExe = $FallbackPath
    }
}

if (-not $PythonExe) {
    Write-Log "Python not found on PATH and not at fallback location." "ERROR"
    Write-Log "Add Python to PATH or update the fallback path in this script." "ERROR"
    exit 1
}

Write-Log "Python: $PythonExe"
Write-Log "Launcher: $LauncherPath"
Write-Log "Repo root: $RepoRoot"

# ---------------------------------------------------------------------------
# Launch the daily session
#
# Uses cmd.exe redirection to append Python stdout+stderr directly to the
# wrapper log file at the OS level. This bypasses the PowerShell pipeline
# entirely — Python's stderr log lines never become ErrorRecord objects,
# $ErrorActionPreference = Stop cannot terminate the wrapper, and output
# is written in real-time without any event-queue or buffering issues.
# Python is launched with -u (unbuffered) so lines appear as they are printed.
# ---------------------------------------------------------------------------
Write-Log "Launching daily session ..."

Set-Location $RepoRoot

cmd.exe /c "`"$PythonExe`" -u `"$LauncherPath`" >> `"$LogFile`" 2>&1"

$ExitCode = $LASTEXITCODE

if ($ExitCode -eq 0) {
    Write-Log "Daily session completed successfully (exit code 0)"
} else {
    Write-Log "Daily session exited with code $ExitCode" "WARN"
}

exit $ExitCode
