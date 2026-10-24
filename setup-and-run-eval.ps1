$ErrorActionPreference = "Stop"

$Root = "C:\dev\bimguard"
if (-not (Test-Path $Root)) {
    Write-Host "[FAIL] $Root does not exist"
    exit 1
}

function Write-NoBom {
    param([string]$Path, [string]$Text)
    $enc = New-Object System.Text.UTF8Encoding($false)
    $dir = Split-Path -Parent $Path
    if ($dir -and -not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    [System.IO.File]::WriteAllText($Path, $Text, $enc)
}

# ============================================================
# 1. Patch evaluate.py BASE_URL -> 127.0.0.1 (IPv4)
# ============================================================
Write-Host "=== Patching evaluate.py ==="
$evalPath = "$Root\scripts\evaluate.py"
if (-not (Test-Path $evalPath)) {
    Write-Host "[FAIL] $evalPath not found"
    exit 1
}
$evalText = [System.IO.File]::ReadAllText($evalPath) -replace "`r`n", "`n"
if ($evalText -match 'BASE_URL = "http://127\.0\.0\.1:8000"') {
    Write-Host "[SKIP] evaluate.py already uses 127.0.0.1"
} elseif ($evalText -match 'BASE_URL = "http://localhost:8000"') {
    $evalText = $evalText.Replace('BASE_URL = "http://localhost:8000"', 'BASE_URL = "http://127.0.0.1:8000"')
    Write-NoBom $evalPath $evalText
    Write-Host "[OK] evaluate.py: BASE_URL -> 127.0.0.1"
} else {
    Write-Host "[FAIL] could not find BASE_URL line in evaluate.py"
    exit 1
}

# ============================================================
# 2. Write run-evaluation.ps1 with hardcoded paths
#    (no $PSScriptRoot, so it works whether or not the parent
#    was invoked correctly)
# ============================================================
Write-Host ""
Write-Host "=== Writing scripts/run-evaluation.ps1 ==="

$inner = @'
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
'@

Write-NoBom "$Root\scripts\run-evaluation.ps1" $inner
Write-Host "[OK] wrote $Root\scripts\run-evaluation.ps1"

# ============================================================
# 3. Validate the written script parses cleanly
#    (this catches here-string truncation on paste)
# ============================================================
Write-Host ""
Write-Host "=== Validating run-evaluation.ps1 parses ==="
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseFile(
    "$Root\scripts\run-evaluation.ps1",
    [ref]$tokens,
    [ref]$errors
) | Out-Null

if ($errors.Count -gt 0) {
    Write-Host "[FAIL] written script has $($errors.Count) parse error(s):" -ForegroundColor Red
    $errors | Select-Object -First 5 | ForEach-Object { Write-Host "  $($_.Message)" }
    Write-Host ""
    Write-Host "This usually means the here-string was truncated during paste."
    Write-Host "Save this script as a file and run it with -File, not pasted."
    exit 1
}
Write-Host "[OK] run-evaluation.ps1 parses"

# ============================================================
# 4. Invoke the evaluation script as a file
# ============================================================
Write-Host ""
Write-Host "======================================================"
Write-Host " Running evaluation"
Write-Host "======================================================"
Write-Host ""

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Root\scripts\run-evaluation.ps1"
$final = $LASTEXITCODE

Write-Host ""
Write-Host "======================================================"
if ($final -eq 0) {
    Write-Host " FINAL: PASS" -ForegroundColor Green
} elseif ($final -eq 2) {
    Write-Host " FINAL: rule mismatch (see results.md)" -ForegroundColor Yellow
} else {
    Write-Host " FINAL: FAILED (exit $final)" -ForegroundColor Red
}
Write-Host "======================================================"

exit $final