<#
 Verify that backups are recent and not failing.

 Checks:
 1. At least one backup file exists
 2. The newest backup is younger than -MaxAgeHours (default 26h, i.e. a
    nightly job that missed one night is still OK, two is not)
 3. last-run.log does not end with a FAILED line (if present)

 Exit 0 if healthy, 1 if not. Prints a diagnostic on failure.
 Designed to be called by monitoring (Healthchecks.io, cron + email, etc).
#>
param(
    [string]$BackupDir = "C:\dev\bimguard\backups",
    [int]$MaxAgeHours = 26
)
$ErrorActionPreference = "Stop"

$failures = @()

if (-not (Test-Path $BackupDir)) {
    Write-Host "[FAIL] backup dir does not exist: $BackupDir" -ForegroundColor Red
    exit 1
}

$backups = @(Get-ChildItem $BackupDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^bimguard-\d{8}-\d{6}\.(db|dump)$" } |
    Sort-Object LastWriteTime -Descending)

if ($backups.Count -eq 0) {
    $failures += "no backup files found in $BackupDir"
} else {
    $newest = $backups[0]
    $age = (Get-Date) - $newest.LastWriteTime
    Write-Host ("newest: {0} ({1:N1}h old)" -f $newest.Name, $age.TotalHours)
    if ($age.TotalHours -gt $MaxAgeHours) {
        $failures += ("newest backup is {0:N1}h old, exceeds {1}h" -f $age.TotalHours, $MaxAgeHours)
    }
    if ($backups.Count -lt 3) {
        Write-Host ("[warn] only {0} backup(s) present; retention may be misconfigured" -f $backups.Count) -ForegroundColor Yellow
    } else {
        Write-Host ("{0} backup(s) present" -f $backups.Count)
    }
}

$logPath = Join-Path $BackupDir "last-run.log"
if (Test-Path $logPath) {
    $tail = Get-Content $logPath -Tail 10 -ErrorAction SilentlyContinue
    if ($tail -match "\[backup-now\] FAILED") {
        $failures += "last-run.log shows a FAILED run"
    }
}

if ($failures.Count -gt 0) {
    Write-Host ""
    Write-Host "[UNHEALTHY]" -ForegroundColor Red
    $failures | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    exit 1
}

Write-Host "[HEALTHY]" -ForegroundColor Green
exit 0