$ErrorActionPreference = "Stop"

$Root = $PSScriptRoot
$ApiDir = Join-Path $Root "apps\api"
$WebDir = Join-Path $Root "apps\web"
$Python = Join-Path $ApiDir ".venv\Scripts\python.exe"

if (-not (Test-Path $Python)) { throw "Python environment missing." }
if (-not (Test-Path (Join-Path $WebDir "node_modules"))) {
    throw "Frontend dependencies missing. Run npm ci inside apps/web."
}

$Npm = (Get-Command npm.cmd -ErrorAction Stop).Source

$RunId = [guid]::NewGuid().ToString("N")
$DbName = "bimguard_e2e_$RunId.db"
$DbPath = Join-Path $ApiDir $DbName

$ApiPort = 8100
$WebPort = 3100

$ApiProcess = $null
$ExitCode = 1

$env:DATABASE_URL = "sqlite:///$DbName"
$env:ENVIRONMENT = "development"
$env:JWT_SECRET = "local-e2e-only-$RunId"
$env:E2E_API_URL = "http://127.0.0.1:$ApiPort"
$env:E2E_WEB_PORT = "$WebPort"
$env:NEXT_PUBLIC_API_URL = $env:E2E_API_URL

try {
    Write-Host "`n[1/5] Migrating isolated database..." -ForegroundColor Cyan

    Push-Location $ApiDir
    try {
        & $Python -m alembic upgrade head
        if ($LASTEXITCODE -ne 0) { throw "Alembic migration failed." }

        $SeedLines = @(
            "from app.db.session import SessionLocal",
            "from app.models.user import User, Role",
            "from app.core.security import hash_password",
            "password = 'admin-demo-pass'",
            "users = [",
            "('admin@example.local', 'Admin', Role.ADMIN),",
            "('coordinator@example.local', 'Coordinator', Role.BIM_COORDINATOR),",
            "('engineer@example.local', 'Engineer', Role.ENGINEER),",
            "('reviewer@example.local', 'Reviewer', Role.REVIEWER),",
            "('viewer@example.local', 'Viewer', Role.VIEWER),",
            "]",
            "with SessionLocal() as db:",
            "    for email, name, role in users:",
            "        if not db.query(User).filter(User.email == email).first():",
            "            db.add(User(email=email, full_name=name, role=role, password_hash=hash_password(password)))",
            "    db.commit()",
            "print('Seeded five E2E users.')"
        )

        $SeedCode = $SeedLines -join "`n"
        $SeedCode | & $Python -
        if ($LASTEXITCODE -ne 0) { throw "E2E account seeding failed." }
    }
    finally {
        Pop-Location
    }

    Write-Host "`n[2/5] Starting API on port $ApiPort..." -ForegroundColor Cyan

    $ApiOut = Join-Path $env:TEMP "bimguard-e2e-$RunId-api.log"
    $ApiErr = Join-Path $env:TEMP "bimguard-e2e-$RunId-api-error.log"

    $ApiProcess = Start-Process `
        -FilePath $Python `
        -ArgumentList @(
            "-m", "uvicorn", "app.main:app",
            "--host", "127.0.0.1",
            "--port", "$ApiPort"
        ) `
        -WorkingDirectory $ApiDir `
        -PassThru `
        -RedirectStandardOutput $ApiOut `
        -RedirectStandardError $ApiErr

    $Ready = $false
    for ($i = 0; $i -lt 40; $i++) {
        if ($ApiProcess.HasExited) {
            throw "API exited. Check $ApiErr"
        }

        try {
            Invoke-RestMethod "http://127.0.0.1:$ApiPort/health" -TimeoutSec 2 | Out-Null
            $Ready = $true
            break
        }
        catch {
            Start-Sleep -Seconds 1
        }
    }

    if (-not $Ready) { throw "API health check timed out." }

    Write-Host "API healthy." -ForegroundColor Green

    Write-Host "`n[3/5] Running Playwright..." -ForegroundColor Cyan

    Push-Location $WebDir
    try {
        & $Npm exec -- playwright test
        $ExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }

    if ($ExitCode -ne 0) {
        Write-Host "Playwright reported failures." -ForegroundColor Red
    }
    else {
        Write-Host "Playwright passed." -ForegroundColor Green
    }
}
catch {
    Write-Host "E2E runner error: $_" -ForegroundColor Red
    $ExitCode = 1
}
finally {
    Write-Host "`n[4/5] Stopping API..." -ForegroundColor Cyan

    if ($null -ne $ApiProcess) {
        try {
            if (-not $ApiProcess.HasExited) {
                Stop-Process -Id $ApiProcess.Id -Force
            }
        }
        catch {
            Write-Warning "Could not stop API process: $_"
        }
    }

    Write-Host "`n[5/5] Removing this run's temporary database..." -ForegroundColor Cyan

    if (Test-Path $DbPath) {
        try {
            Remove-Item -LiteralPath $DbPath -Force
        }
        catch {
            Write-Warning "Temporary database could not be removed: $DbPath"
        }
    }
}

exit $ExitCode
