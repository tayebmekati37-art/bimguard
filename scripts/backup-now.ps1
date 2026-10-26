<#
 Run one backup. Designed to be invoked by a scheduler (Task Scheduler
 or cron) or manually. Does not depend on the API being up.

 Usage:
   scripts\backup-now.ps1
   scripts\backup-now.ps1 -RetentionDays 60
   scripts\backup-now.ps1 -OffSite "file:///D:/backups/bimguard"
   scripts\backup-now.ps1 -OffSite "s3://my-bucket/bimguard"

 Reads DATABASE_URL from .env (or env). Reads BACKUP_OFF_SITE and
 BACKUP_RETENTION_DAYS from env if set. Writes a JSON log line.

 Exit codes:
   0  success
   1  backup failed
   2  backup succeeded, off-site copy failed
#>
param(
    [int]$RetentionDays = 0,
    [string]$OffSite = "",
    [string]$OutputDir = "C:\dev\bimguard\backups"
)
$ErrorActionPreference = "Stop"

$root = "C:\dev\bimguard"
$py = "$root\apps\api\.venv\Scripts\python.exe"
$runner = "$root\scripts\backup_runner.py"
$log = Join-Path $OutputDir "last-run.log"

if (-not (Test-Path $py)) {
    Write-Host "[FAIL] venv python not found: $py"
    exit 1
}
if (-not (Test-Path $runner)) {
    Write-Host "[FAIL] backup_runner.py not found: $runner"
    exit 1
}

if (-not (Test-Path $OutputDir)) {
    New-Item -ItemType Directory -Path $OutputDir -Force | Out-Null
}

# Defaults from env if not passed as parameters
if ($RetentionDays -le 0) {
    $envVal = $env:BACKUP_RETENTION_DAYS
    if ($envVal -and [int]::TryParse($envVal, [ref]0)) {
        $RetentionDays = [int]$envVal
    } else {
        $RetentionDays = 30
    }
}
if (-not $OffSite) {
    $OffSite = if ($env:BACKUP_OFF_SITE) { $env:BACKUP_OFF_SITE } else { "" }
}

$timestamp = Get-Date -Format "yyyy-MM-ddTHH:mm:ssK"
$header = "=== backup-now $timestamp ==="
Write-Host $header
$header | Out-File -FilePath $log -Append -Encoding utf8

# Run
$old = $ErrorActionPreference
$ErrorActionPreference = "Continue"
$output = & $py $runner --output-dir $OutputDir --retention-days $RetentionDays --off-site $OffSite 2>&1
$code = $LASTEXITCODE
$ErrorActionPreference = $old

$output | Out-File -FilePath $log -Append -Encoding utf8
$output | ForEach-Object { Write-Host $_ }

$footer = "=== exit: $code at $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ssK') ==="
$footer | Out-File -FilePath $log -Append -Encoding utf8
Write-Host $footer

if ($code -eq 0) {
    Write-Host "[backup-now] OK" -ForegroundColor Green
} elseif ($code -eq 2) {
    Write-Host "[backup-now] PARTIAL (backup OK, off-site failed)" -ForegroundColor Yellow
} else {
    Write-Host "[backup-now] FAILED" -ForegroundColor Red
}
exit $code