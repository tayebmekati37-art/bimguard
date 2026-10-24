$ErrorActionPreference = "Stop"

$Root = "C:\dev\bimguard"
$ApiDir = "$Root\apps\api"
$ApiPython = "$ApiDir\.venv\Scripts\python.exe"
$EvaluateScript = "$Root\scripts\evaluate.py"
$ApiOutLog = "$env:TEMP\bimguard-api-stdout.log"
$ApiErrLog = "$env:TEMP\bimguard-api-stderr.log"
$HealthUrl = "http://127.0.0.1:8000/health"

if (-not (Test-Path $ApiPython)) {
    Write-Host "[FAIL] $ApiPython not found"
    exit 1
}
if (-not (Test-Path $EvaluateScript)) {
    Write-Host "[FAIL] $EvaluateScript not found"
    exit 1
}

function Test-ApiReady {
    try {
        $r = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 2
        return $r.StatusCode -eq 200
    } catch {
        return $false
    }
}

$apiProc = $null

if (Test-ApiReady) {
    Write-Host "API already running on :8000; using the existing instance."
} else {
    Write-Host "API not running. Starting uvicorn via Start-Process..."
    Write-Host "  stdout -> $ApiOutLog"
    Write-Host "  stderr -> $ApiErrLog"

    $apiProc = Start-Process -FilePath $ApiPython `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000" `
        -WorkingDirectory $ApiDir `
        -RedirectStandardOutput $ApiOutLog `
        -RedirectStandardError $ApiErrLog `
        -NoNewWindow `
        -PassThru

    Write-Host "  uvicorn PID: $($apiProc.Id)"

    $ready = $false
    $elapsed = 0
    for ($i = 0; $i -lt 60; $i++) {
        Start-Sleep -Seconds 1
        $elapsed = $i + 1
        if ($apiProc.HasExited) {
            Write-Host "[FAIL] uvicorn exited (code $($apiProc.ExitCode)) before binding" -ForegroundColor Red
            break
        }
        if (Test-ApiReady) { $ready = $true; break }
    }

    if (-not $ready) {
        Write-Host "[FAIL] API did not become healthy within 60s" -ForegroundColor Red
        Write-Host ""
        Write-Host "--- stdout ($ApiOutLog) ---"
        if (Test-Path $ApiOutLog) {
            Get-Content $ApiOutLog -Tail 40 | ForEach-Object { Write-Host $_ }
        } else {
            Write-Host "(no file)"
        }
        Write-Host ""
        Write-Host "--- stderr ($ApiErrLog) ---"
        if (Test-Path $ApiErrLog) {
            Get-Content $ApiErrLog -Tail 40 | ForEach-Object { Write-Host $_ }
        } else {
            Write-Host "(no file)"
        }
        if ($apiProc -and -not $apiProc.HasExited) {
            Write-Host ""
            Write-Host "Killing uvicorn PID $($apiProc.Id)..."
            Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
        }
        exit 1
    }
    Write-Host "API is up (took $elapsed seconds)."
}

Write-Host ""
Write-Host "=== Running evaluation ==="
$evalExit = 0
try {
    & $ApiPython $EvaluateScript
    $evalExit = $LASTEXITCODE
} finally {
    if ($apiProc -and -not $apiProc.HasExited) {
        Write-Host ""
        Write-Host "Stopping uvicorn PID $($apiProc.Id)..."
        Stop-Process -Id $apiProc.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Milliseconds 500
    }
}

Write-Host ""
if ($evalExit -eq 0) {
    Write-Host "RESULT: PASS - every measured rule matched; readiness matched." -ForegroundColor Green
    Write-Host "See docs/evaluation/results.md"
} elseif ($evalExit -eq 2) {
    Write-Host "RESULT: rule mismatch - see docs/evaluation/results.md" -ForegroundColor Yellow
} else {
    Write-Host "RESULT: evaluation failed (exit $evalExit)" -ForegroundColor Red
}

exit $evalExit