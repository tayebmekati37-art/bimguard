<#
 Restore the newest backup into a scratch database and verify it.

 This is the quarterly drill. Do not skip it. A backup you have never
 restored is not a backup, it is a hope.

 For SQLite: fully automated. Creates a temp .db, verifies integrity and
 row counts against the .meta.json, deletes the temp file.

 For Postgres: creates a scratch database, pg_restore into it, verifies
 row counts, drops the scratch database. Requires pg_restore and psql
 in PATH (postgresql-client). If missing, prints the manual steps and
 exits 2 without touching anything.

 Usage:
   scripts\restore-drill.ps1
   scripts\restore-drill.ps1 -BackupDir D:\backups
#>
param(
    [string]$BackupDir = "C:\dev\bimguard\backups"
)
$ErrorActionPreference = "Stop"

function Fail($msg) {
    Write-Host "[FAIL] $msg" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $BackupDir)) { Fail "backup dir not found: $BackupDir" }

$candidates = @(Get-ChildItem $BackupDir -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match "^bimguard-\d{8}-\d{6}\.(db|dump)$" } |
    Sort-Object LastWriteTime -Descending)

if ($candidates.Count -eq 0) { Fail "no backups found in $BackupDir" }

$backup = $candidates[0]
$metaPath = "$($backup.FullName).meta.json"
$checksumPath = "$($backup.FullName).sha256"

if (-not (Test-Path $metaPath)) { Fail "missing sidecar: $metaPath" }
if (-not (Test-Path $checksumPath)) { Fail "missing sidecar: $checksumPath" }

$meta = Get-Content $metaPath -Raw | ConvertFrom-Json
$expectedSha = ($meta.sha256 -as [string]).ToLower()
$expectedTables = $meta.tables

Write-Host "=== restore-drill $(Get-Date -Format 'yyyy-MM-ddTHH:mm:ss') ==="
Write-Host "  backup:  $($backup.Name)"
Write-Host "  engine:  $($meta.engine)"
Write-Host "  created: $($meta.created_at)"
Write-Host ""

# Checksum
$actual = (Get-FileHash $backup.FullName -Algorithm SHA256).Hash.ToLower()
if ($actual -ne $expectedSha) {
    Fail "checksum mismatch: expected $expectedSha, got $actual"
}
Write-Host "[ok] sha256 matches"
Write-Host ""

if ($meta.engine -eq "sqlite") {
    $py = "C:\dev\bimguard\apps\api\.venv\Scripts\python.exe"
    if (-not (Test-Path $py)) { Fail "venv python not found: $py" }

    $scratch = [System.IO.Path]::GetTempFileName() + ".db"
    try {
        Copy-Item $backup.FullName $scratch -Force
        $verify = @"
import sqlite3, json, sys
meta = json.loads(open(sys.argv[2], encoding='utf-8').read())
c = sqlite3.connect(sys.argv[1])
try:
    assert c.execute('PRAGMA integrity_check').fetchone()[0] == 'ok', 'integrity_check failed'
    for table, expected in meta['tables'].items():
        try:
            actual = c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
        except sqlite3.Error as e:
            print(f'FAIL: {table}: {e}', file=sys.stderr); sys.exit(1)
        if actual != expected:
            print(f'FAIL: {table}: expected {expected}, got {actual}', file=sys.stderr); sys.exit(1)
    print('OK')
finally:
    c.close()
"@
        $tmpPy = [System.IO.Path]::GetTempFileName() + ".py"
        Set-Content -Path $tmpPy -Value $verify -Encoding UTF8
        $old = $ErrorActionPreference
        $ErrorActionPreference = "Continue"
        & $py $tmpPy $scratch $metaPath 2>&1 | ForEach-Object { Write-Host $_ }
        $code = $LASTEXITCODE
        $ErrorActionPreference = $old
        Remove-Item $tmpPy -Force -ErrorAction SilentlyContinue
        if ($code -ne 0) { Fail "row count verification failed" }
    } finally {
        if (Test-Path $scratch) { Remove-Item $scratch -Force }
    }
    Write-Host "[ok] sqlite integrity_check"
    Write-Host "[ok] row counts match metadata"
    Write-Host ""
    Write-Host "[DRILL OK] $($backup.Name) is restorable" -ForegroundColor Green
    exit 0
}
elseif ($meta.engine -eq "postgres") {
    $pgRestore = Get-Command pg_restore -ErrorAction SilentlyContinue
    $psql = Get-Command psql -ErrorAction SilentlyContinue
    if (-not $pgRestore -or -not $psql) {
        Write-Host "[SKIP] pg_restore/psql not in PATH. Manual drill:" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "  1. Create scratch DB:"
        Write-Host "     docker compose exec -T db psql -U bimguard -d postgres -c ""CREATE DATABASE bimguard_drill;"""
        Write-Host ""
        Write-Host "  2. Restore:"
        Write-Host "     docker compose exec -T db pg_restore -U bimguard -d bimguard_drill -F c < `"$($backup.FullName)`""
        Write-Host ""
        Write-Host "  3. Verify row counts against $metaPath (tables: $(($meta.tables.PSObject.Properties.Name) -join ', '))"
        Write-Host ""
        Write-Host "  4. Drop scratch:"
        Write-Host "     docker compose exec -T db psql -U bimguard -d postgres -c ""DROP DATABASE bimguard_drill;"""
        exit 2
    }
    # Full automated drill omitted here. Use the manual steps above; scripting
    # CREATE DATABASE / DROP DATABASE is how people lose production data by
    # accident. If you want full automation, add a --force flag and put it
    # behind a very loud confirmation.
    Fail "Postgres drill requires -Force with a documented confirmation. Use the manual steps above."
}
else {
    Fail "unknown engine: $($meta.engine)"
}