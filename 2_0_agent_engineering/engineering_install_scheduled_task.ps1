# engineering_install_scheduled_task.ps1
#
# One-time installer for the Windows Task Scheduler task that runs the
# intraday_same_day Alpaca paper trading launcher Monday-Friday at 09:00 AM ET.
#
# Prerequisites:
#   - .claude/settings.local.json must contain ALPACA_API_KEY, ALPACA_API_SECRET,
#     APCA_API_BASE_URL in its env block (credentials are NOT stored in this script)
#   - Python must be on PATH or present at the fallback path in the wrapper script
#
# Usage — install:
#   powershell -ExecutionPolicy Bypass -File engineering_install_scheduled_task.ps1
#
# Usage — uninstall:
#   Unregister-ScheduledTask -TaskName "AlpacaPaper_IntraDay_SameDay_Launcher" -Confirm:$false
#
# Dry-run vs paper-order mode is controlled by alpaca_submit_orders in the YAML config.
# This script does not touch the config — flip that one flag independently.

$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
$ScriptDir    = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RepoRoot     = Split-Path -Parent $ScriptDir
$WrapperPath  = Join-Path $ScriptDir "engineering_launcher_wrapper.ps1"

# ---------------------------------------------------------------------------
# Validate wrapper exists before registering
# ---------------------------------------------------------------------------
if (-not (Test-Path $WrapperPath)) {
    Write-Error "Wrapper script not found: $WrapperPath"
    Write-Error "Run this installer from the 2_0_agent_engineering/ directory."
    exit 1
}

# ---------------------------------------------------------------------------
# Task settings
# ---------------------------------------------------------------------------
$TaskName    = "AlpacaPaper_IntraDay_SameDay_Launcher"
$TaskDescr   = "Intraday same-day Alpaca paper trading launcher. Runs premarket, polls session, exits EOD."
$StartTime   = "09:00"

# Run as the current logged-in user (no admin elevation needed for paper trading)
$RunAsUser   = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

# ---------------------------------------------------------------------------
# Build the scheduled task action
# ---------------------------------------------------------------------------
$Action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NonInteractive -ExecutionPolicy Bypass -File `"$WrapperPath`"" `
    -WorkingDirectory $RepoRoot

# ---------------------------------------------------------------------------
# Build the trigger: Mon-Fri at 09:00 AM (daily trigger + day-of-week filter)
# ---------------------------------------------------------------------------
$Trigger = New-ScheduledTaskTrigger `
    -Weekly `
    -DaysOfWeek Monday, Tuesday, Wednesday, Thursday, Friday `
    -At $StartTime

# ---------------------------------------------------------------------------
# Settings: allow task to run up to 8 hours, stop if already running
# ---------------------------------------------------------------------------
$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 8) `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

# ---------------------------------------------------------------------------
# Principal: current user, run whether or not logged on is optional;
# here we use "run only when logged on" so no password needs to be stored.
# ---------------------------------------------------------------------------
$Principal = New-ScheduledTaskPrincipal `
    -UserId $RunAsUser `
    -LogonType Interactive `
    -RunLevel Limited

# ---------------------------------------------------------------------------
# Register (create or overwrite)
# ---------------------------------------------------------------------------
$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue

if ($Existing) {
    Write-Host "Task '$TaskName' already exists -- overwriting ..."
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
}

Register-ScheduledTask `
    -TaskName    $TaskName `
    -Description $TaskDescr `
    -Action      $Action `
    -Trigger     $Trigger `
    -Settings    $Settings `
    -Principal   $Principal | Out-Null

Write-Host ""
Write-Host "Task registered successfully."
Write-Host "  Task name  : $TaskName"
Write-Host "  Schedule   : Monday-Friday at $StartTime ET"
Write-Host "  Wrapper    : $WrapperPath"
Write-Host "  Working dir: $RepoRoot"
Write-Host "  Runs as    : $RunAsUser"
Write-Host ""
Write-Host "Verify in Task Scheduler:"
Write-Host "  Get-ScheduledTask -TaskName '$TaskName' | Select-Object TaskName, State"
Write-Host ""
Write-Host "Test run now (optional):"
Write-Host "  Start-ScheduledTask -TaskName '$TaskName'"
Write-Host ""
Write-Host "Uninstall:"
Write-Host "  Unregister-ScheduledTask -TaskName '$TaskName' -Confirm:`$false"
