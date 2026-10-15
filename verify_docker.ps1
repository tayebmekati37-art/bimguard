$ErrorActionPreference = "Stop"

Write-Host "=== BIMGuard Docker verification ==="
Write-Host ""

# 1. Docker present?
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "[FAIL] docker not found in PATH"
    exit 1
}

$composeFile = $null
foreach ($name in @("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")) {
    if (Test-Path -LiteralPath "C:\dev\bimguard\$name") {
        $composeFile = $name
        break
    }
}
if (-not $composeFile) {
    Write-Host "[FAIL] no compose file found in C:\dev\bimguard"
    exit 1
}
Write-Host "[OK] compose file: $composeFile"

Set-Location C:\dev\bimguard

# 2. Prepare .env
if (-not (Test-Path -LiteralPath ".env")) {
    if (Test-Path -LiteralPath ".env.example") {
        Copy-Item .env.example .env
        Write-Host "[OK] created .env from .env.example"
    } else {
        Write-Host "[WARN] no .env or .env.example - proceeding with compose defaults"
    }
} else {
    Write-Host "[OK] .env exists"
}

# 3. Validate config
Write-Host ""
Write-Host "=== docker compose config ==="
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] compose config invalid"; exit 1 }
Write-Host "[OK] compose config valid"

# 4. Build
Write-Host ""
Write-Host "=== docker compose build ==="
docker compose build
if ($LASTEXITCODE -ne 0) { Write-Host "[FAIL] build failed"; exit 1 }
Write-Host "[OK] images built"

# 5. Start
Write-Host ""
Write-Host "=== docker compose up -d ==="
docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Host "[FAIL] up failed; logs follow"
    docker compose logs --tail=100
    exit 1
}

# 6. Wait for backend health on :8000
Write-Host ""
Write-Host "=== waiting for backend health on http://localhost:8000/health ==="
$ready = $false
for ($i = 0; $i -lt 45; $i++) {
    Start-Sleep -Seconds 2
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 3
        if ($r.StatusCode -eq 200) { $ready = $true; break }
    } catch {}
}
if (-not $ready) {
    Write-Host "[FAIL] backend never became healthy"
    docker compose logs --tail=100
    docker compose down
    exit 1
}
Write-Host "[OK] backend healthy"

# 7. Frontend check on :3000 (best-effort; Next.js may still compile)
Write-Host ""
Write-Host "=== frontend check on http://localhost:3000 ==="
try {
    $r = Invoke-WebRequest -Uri "http://localhost:3000" -UseBasicParsing -TimeoutSec 10
    Write-Host "[OK] frontend responded ($($r.StatusCode))"
} catch {
    Write-Host "[WARN] frontend did not respond within timeout (may still be compiling): $($_.Exception.Message)"
}

# 8. Tear down
Write-Host ""
Write-Host "=== docker compose down ==="
docker compose down

Write-Host ""
Write-Host "[DONE] Docker verification complete"