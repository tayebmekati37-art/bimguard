<#
 Restore a BIMGuard native backup.

 SQLite: fully automated. Verifies checksum, integrity, and metadata, then
 swaps the DB file. Requires -Force to actually overwrite the live DB.

 Postgres: generates the exact pg_restore procedure for the operator to
 run. Does not execute it. This is deliberate; scripting a destructive
 operation on production Postgres is asking for a disaster.

 Usage:
   .\restore.ps1 -BackupPath storage\backups\bimguard-20261022-120000.db -WhatIf
   .\restore.ps1 -BackupPath storage\backups\bimguard-20261022-120000.db -Force
#>
param(
    [Parameter(Mandatory=$true)][string]$BackupPath,
    [switch]$Force,
    [switch]$WhatIf
)
$ErrorActionPreference = "Stop"

function Get-Sha256($path) {
    (Get-FileHash -Path $path -Algorithm SHA256).Hash.ToLower()
}

function Fail($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    exit 1
}

# ------------------------------------------------------------------ inspect
if (-not (Test-Path -LiteralPath $BackupPath)) {
    Fail "Backup file not found: $BackupPath"
}
$BackupPath = (Resolve-Path -LiteralPath $BackupPath).Path

$metaPath = "$BackupPath.meta.json"
$checksumPath = "$BackupPath.sha256"

if (-not (Test-Path -LiteralPath $metaPath)) {
    Fail "Missing metadata sidecar: $metaPath`nThis is not a BIMGuard native backup."
}
if (-not (Test-Path -LiteralPath $checksumPath)) {
    Fail "Missing checksum sidecar: $checksumPath`nCannot verify integrity without a checksum."
}

$meta = Get-Content -LiteralPath $metaPath -Raw | ConvertFrom-Json
$expectedSha = ($meta.sha256 -as [string]).ToLower()
if (-not $expectedSha) { Fail "meta.json missing sha256 field" }

Write-Host "=== Backup inspection ===" -ForegroundColor Cyan
Write-Host "  Path:            $BackupPath"
Write-Host "  Engine:          $($meta.engine)"
Write-Host "  Created at:      $($meta.created_at)"
Write-Host "  Alembic rev:     $($meta.alembic_revision)"
Write-Host "  App version:     $($meta.app_version)"
Write-Host "  Size (bytes):    $($meta.file_size_bytes)"
Write-Host "  Tables:"
$meta.tables.PSObject.Properties | Sort-Object Name | ForEach-Object {
    Write-Host ("    {0,-30} {1}" -f $_.Name, $_.Value)
}
Write-Host ""

# ------------------------------------------------------------------ checksum
Write-Host "=== Verifying checksum ===" -ForegroundColor Cyan
$actualSha = Get-Sha256 $BackupPath
if ($actualSha -ne $expectedSha) {
    Fail "Checksum mismatch.`n  expected: $expectedSha`n  actual:   $actualSha`nThe backup is corrupt or has been modified."
}
Write-Host "  [ ok ] sha256 = $actualSha"
Write-Host ""

# ------------------------------------------------------------------ engine-specific
if ($meta.engine -eq "sqlite") {
    # Integrity check
    Write-Host "=== Verifying SQLite integrity ===" -ForegroundColor Cyan
    $check = & python -c "import sqlite3,sys; c=sqlite3.connect(sys.argv[1]); print(c.execute('PRAGMA integrity_check').fetchone()[0]); c.close()" "$BackupPath"
    if ($LASTEXITCODE -ne 0) { Fail "sqlite3 integrity check errored" }
    if ($check.Trim() -ne "ok") {
        Fail "SQLite integrity check returned: $check"
    }
    Write-Host "  [ ok ] PRAGMA integrity_check = ok"
    Write-Host ""

    # Determine current DB path
    $dbUrl = $env:DATABASE_URL
    if (-not $dbUrl) {
        # Fall back to reading .env if present
        $envPath = Join-Path (Split-Path -Parent $PSScriptRoot) "apps\api\.env"
        if (Test-Path $envPath) {
            $line = Select-String -Path $envPath -Pattern "^DATABASE_URL=" | Select-Object -First 1
            if ($line) { $dbUrl = ($line.Line -replace "^DATABASE_URL=", "").Trim('"', "'") }
        }
    }
    if (-not $dbUrl) { $dbUrl = "sqlite:///./bimguard_dev.db" }
    if ($dbUrl -notmatch "^sqlite") {
        Fail "This backup was made from SQLite but DATABASE_URL is: $dbUrl`nSet DATABASE_URL=sqlite:///./your.db to restore it, or use the Postgres procedure."
    }

    $dbRelPath = $dbUrl -replace "^sqlite:/*/", ""
    $dbPath = [System.IO.Path]::GetFullPath((Join-Path (Get-Location) $dbRelPath))
    Write-Host "Target SQLite file: $dbPath"

    if (Test-Path -LiteralPath $dbPath) {
        Write-Host "  Current DB exists. Will be preserved as: $dbPath.before-restore-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    }

    if ($WhatIf) {
        Write-Host ""
        Write-Host "[WhatIf] Would:" -ForegroundColor Yellow
        Write-Host "  1. Copy $BackupPath -> $dbPath"
        Write-Host "  2. Move current DB aside"
        Write-Host "  3. Verify row counts against metadata"
        exit 0
    }

    if (-not $Force) {
        Write-Host ""
        Write-Host "[FAIL] Refusing to overwrite without -Force." -ForegroundColor Red
        Write-Host "Re-run with -Force to execute the restore, or -WhatIf to preview."
        exit 1
    }

    # Move current DB aside (if it exists)
    if (Test-Path -LiteralPath $dbPath) {
        $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
        $preserved = "$dbPath.before-restore-$stamp"
        Write-Host "  Preserving current DB as: $preserved"
        Move-Item -LiteralPath $dbPath -Destination $preserved -Force
    } else {
        Write-Host "  No current DB at target path; nothing to preserve."
    }

    # Copy backup in place
    Write-Host "  Copying backup to $dbPath"
    Copy-Item -LiteralPath $BackupPath -Destination $dbPath

    # Verify row counts
    Write-Host ""
    Write-Host "=== Verifying row counts ===" -ForegroundColor Cyan
    $dbPathPy = $dbPath -replace "\\", "/"
    $countPy = @"
import sqlite3, json, sys
c = sqlite3.connect(r'$dbPathPy')
tables = json.loads('''$($meta.tables | ConvertTo-Json -Compress)''')
mismatches = []
for name, expected in tables.items():
    try:
        actual = c.execute(f'SELECT count(*) FROM {name}').fetchone()[0]
    except sqlite3.Error as e:
        mismatches.append(f'{name}: {e}')
        continue
    if actual != expected:
        mismatches.append(f'{name}: expected {expected}, got {actual}')
    else:
        print(f'  [ ok ] {name:<30} {actual}')
c.close()
if mismatches:
    print('MISMATCHES:')
    for m in mismatches: print('  ' + m)
    sys.exit(1)
"@
    $tmp = [System.IO.Path]::GetTempFileName() + ".py"
    Set-Content -Path $tmp -Value $countPy -Encoding UTF8
    & python $tmp
    $countExit = $LASTEXITCODE
    Remove-Item $tmp -Force

    if ($countExit -ne 0) {
        Fail "Row counts do not match the backup metadata. The restore is incomplete."
    }

    Write-Host ""
    Write-Host "[OK] Restore complete" -ForegroundColor Green
    Write-Host ""
    Write-Host "Restart the API to pick up the restored database."
    exit 0
}
elseif ($meta.engine -eq "postgres") {
    Write-Host "=== Postgres restore procedure ===" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "This script does not execute the Postgres restore for you."
    Write-Host "That is deliberate: pg_restore into a live database is destructive"
    Write-Host "and should not be scripted. Run these commands manually, in order."
    Write-Host ""
    Write-Host "  1. Stop the API:" -ForegroundColor Yellow
    Write-Host "       docker compose stop api"
    Write-Host ""
    Write-Host "  2. Drop and recreate the database:" -ForegroundColor Yellow
    Write-Host "       docker compose exec -T db psql -U bimguard -d postgres -c `"DROP DATABASE IF EXISTS bimguard;`""
    Write-Host "       docker compose exec -T db psql -U bimguard -d postgres -c `"CREATE DATABASE bimguard;`""
    Write-Host ""
    Write-Host "  3. Restore from this backup:" -ForegroundColor Yellow
    Write-Host "       docker compose exec -T db pg_restore -U bimguard -d bimguard -F c < `"$BackupPath`""
    Write-Host ""
    Write-Host "  4. Start the API:" -ForegroundColor Yellow
    Write-Host "       docker compose start api"
    Write-Host ""
    Write-Host "  5. Verify row counts match the metadata above." -ForegroundColor Yellow
    Write-Host "     Expected counts are printed at the top of this script."
    Write-Host ""
    Write-Host "If any step fails, stop and inspect before continuing. Do not"
    Write-Host "re-run the DROP against a partially-restored database."
    exit 0
}
else {
    Fail "Unknown engine in metadata: $($meta.engine)"
}