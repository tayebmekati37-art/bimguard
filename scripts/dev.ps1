<#
 BIMGuard one-shot local setup and start (Windows / PowerShell).
 Run from anywhere:
   powershell -ExecutionPolicy Bypass -File C:\dev\bimguard\scripts\dev.ps1
 Optional: add -SkipTests to skip pytest.
#>
param([switch]$SkipTests)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api  = Join-Path $root "apps\api"
$web  = Join-Path $root "apps\web"

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user    = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }

# 1. Prerequisites
Step "Checking Python"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3.11+ not found. Install it (python.org, tick 'Add to PATH') and run this script again."
}
$pyver = (python --version) -replace "Python ", ""
if ([version]$pyver -lt [version]"3.11") { throw "Python $pyver found; 3.11 or newer is required." }
Write-Host "Python $pyver OK"

Step "Checking Node.js"
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "Node.js not found and winget is unavailable. Install the LTS version from https://nodejs.org and run this script again."
    }
    Write-Host "Node.js not found. Installing LTS with winget (this may ask for permission)..."
    winget install OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    Refresh-Path
    if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
        throw "Node.js was installed but is not visible yet. Close this window, open a new PowerShell, and run the script again."
    }
}
Write-Host "Node $(node --version) OK"

# 2. API
Step "Setting up the API"
Set-Location $api
if (-not (Test-Path ".venv")) { python -m venv .venv }
$py = Join-Path $api ".venv\Scripts\python.exe"
& $py -m pip install --disable-pip-version-check -q -e ".[dev]"
if ($LASTEXITCODE -ne 0) { throw "pip install failed. See the error above." }
# Database migrations (Alembic). The first run generates the initial migration if none exists yet.
$versions = Join-Path $api "alembic\versions"
if (-not (Get-ChildItem $versions -Filter "*.py" -ErrorAction SilentlyContinue)) {
    Write-Host "No migration found. Generating the initial schema migration (dev database is reset)."
    Remove-Item (Join-Path $api "bimguard_dev.db") -ErrorAction SilentlyContinue
    & $py -m alembic revision --autogenerate -m "initial schema"
    if ($LASTEXITCODE -ne 0) { throw "Could not generate the initial migration." }
}
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Database migration failed. See the error above." }
& $py -m app.seed
if ($LASTEXITCODE -ne 0) { throw "Seeding demo users failed." }

if (-not $SkipTests) {
    Step "Running API tests"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "API tests failed. Fix them before continuing." }
}

# 3. Web
Step "Setting up the web app"
Set-Location $web
if (-not (Test-Path ".env.local")) { Copy-Item ".env.local.example" ".env.local" }
npm.cmd install
if ($LASTEXITCODE -ne 0) { throw "npm install failed. See the error above." }

# 4. Start both servers in their own windows
Step "Starting servers"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$api'; & '$py' -m uvicorn app.main:app --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$web'; npm.cmd run dev"

Start-Sleep -Seconds 8
Start-Process "http://localhost:3000"

Write-Host "`nBIMGuard is starting." -ForegroundColor Green
Write-Host "Web:      http://localhost:3000"
Write-Host "API docs: http://localhost:8000/docs"
Write-Host "Demo login: engineer@example.local / engineer-demo-pass"
Write-Host "Close the two server windows to stop."
