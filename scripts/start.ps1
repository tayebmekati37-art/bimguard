$root = Split-Path -Parent $PSScriptRoot
$api  = Join-Path $root "apps\api"
$web  = Join-Path $root "apps\web"
$py   = Join-Path $api ".venv\Scripts\python.exe"

Set-Location $api
if (-not (Get-ChildItem (Join-Path $api "alembic\versions") -Filter "*.py" -ErrorAction SilentlyContinue)) {
    Remove-Item (Join-Path $api "bimguard_dev.db") -ErrorAction SilentlyContinue
    & $py -m alembic revision --autogenerate -m "initial schema"
}
& $py -m alembic upgrade head
& $py -m app.seed

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$api'; & '$py' -m uvicorn app.main:app --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$web'; npm.cmd run dev"

Start-Sleep -Seconds 8
Start-Process "http://localhost:3000"
Write-Host "API: http://localhost:8000/docs   Web: http://localhost:3000"
Write-Host "Login: admin@example.local / admin-demo-pass"
