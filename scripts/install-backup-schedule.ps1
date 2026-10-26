<#
 Install the nightly backup on Windows Task Scheduler, or print the
 equivalent cron line for Linux/macOS.

 Windows:
   scripts\install-backup-schedule.ps1
   scripts\install-backup-schedule.ps1 -Time "03:30"
   scripts\install-backup-schedule.ps1 -Uninstall

 Linux/macOS:
   scripts\install-backup-schedule.ps1 -PrintCron
#>
param(
    [string]$Time = "02:00",
    [switch]$Uninstall,
    [switch]$PrintCron
)
$ErrorActionPreference = "Stop"

$taskName = "BIMGuard Backup"
$scriptPath = "C:\dev\bimguard\scripts\backup-now.ps1"

if ($PrintCron) {
    $py = "C:\dev\bimguard\apps\api\.venv\Scripts\python.exe"
    # On Linux/macOS the venv python is at a different path; user edits.
    Write-Host "# Add to crontab (crontab -e). Adjust paths for your system."
    Write-Host "# Runs nightly at 02:00. Log goes to backups/last-run.log."
    Write-Host "0 2 * * * /path/to/apps/api/.venv/bin/python /path/to/scripts/backup_runner.py --output-dir /path/to/backups --retention-days 30 >> /path/to/backups/cron.log 2>&1"
    exit 0
}

if ($Uninstall) {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
        Write-Host "[OK] removed task: $taskName"
    } else {
        Write-Host "[SKIP] task not found: $taskName"
    }
    exit 0
}

if (-not (Test-Path $scriptPath)) {
    Write-Host "[FAIL] script not found: $scriptPath"
    exit 1
}

# Validate time format
if ($Time -notmatch "^\d{1,2}:\d{2}$") {
    Write-Host "[FAIL] -Time must be HH:mm, got: $Time"
    exit 1
}

# Remove any existing task of the same name
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Host "[info] removed existing task before re-installing"
}

$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

$trigger = New-ScheduledTaskTrigger -Daily -At $Time

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10)

$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType S4U `
    -RunLevel Limited

Register-ScheduledTask `
    -TaskName $taskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Nightly BIMGuard backup (runs backup-now.ps1). See docs/operations/backup-runbook.md."

Write-Host "[OK] installed scheduled task '$taskName' running daily at $Time"
Write-Host ""
Write-Host "Verify:"
Write-Host "  Get-ScheduledTask -TaskName '$taskName' | Format-List"
Write-Host "  Get-ScheduledTaskInfo -TaskName '$taskName'"
Write-Host ""
Write-Host "Run once now to test:"
Write-Host "  Start-ScheduledTask -TaskName '$taskName'"
Write-Host ""
Write-Host "Then check the log:"
Write-Host "  Get-Content C:\dev\bimguard\backups\last-run.log -Tail 20"