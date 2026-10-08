<#
 BIMGuard Milestone 2 check: pytest + migrations + start servers + scripted demo flow.
 Run:  powershell -ExecutionPolicy Bypass -File C:\dev\bimguard\scripts\test-m2.ps1
 Options: -SkipPytest   -NoBrowser
#>
param([switch]$SkipPytest, [switch]$NoBrowser, [string]$ApiUrl = "http://localhost:8000")

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api  = Join-Path $root "apps\api"
$web  = Join-Path $root "apps\web"
$py   = Join-Path $api ".venv\Scripts\python.exe"
$script:fails = 0

function Step($m) { Write-Host "`n==> $m" -ForegroundColor Cyan }
function Check($Name, [bool]$Ok, $Detail = "") {
    if ($Ok) { Write-Host "  [PASS] $Name" -ForegroundColor Green }
    else { Write-Host "  [FAIL] $Name $Detail" -ForegroundColor Red; $script:fails++ }
}
function Test-Port($Port) {
    try { $c = New-Object Net.Sockets.TcpClient; $c.Connect("127.0.0.1", $Port); $c.Close(); return $true } catch { return $false }
}
function Wait-Url($Url, $Seconds) {
    for ($i = 0; $i -lt $Seconds; $i++) {
        try { Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 2 | Out-Null; return $true } catch { Start-Sleep -Seconds 1 }
    }
    return $false
}
function Call($Method, $Path, $Token, $Body, $Form) {
    $headers = @{}
    if ($Token) { $headers["Authorization"] = "Bearer $Token" }
    $params = @{ Uri = "$ApiUrl$Path"; Method = $Method; Headers = $headers; UseBasicParsing = $true }
    if ($Form) { $params.Body = $Form }
    elseif ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = "application/json" }
    try {
        $r = Invoke-WebRequest @params
        $data = $null
        if ($r.Content) { $data = $r.Content | ConvertFrom-Json }
        return [pscustomobject]@{ Status = [int]$r.StatusCode; Data = $data }
    } catch {
        $code = 0
        if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
        $data = $null
        try { $data = $_.ErrorDetails.Message | ConvertFrom-Json } catch {}
        return [pscustomobject]@{ Status = $code; Data = $data }
    }
}
function Upload($DocId, $Token, $File, $Fields) {
    $out = Join-Path $env:TEMP "bimguard_upload_result.json"
    $a = @("-s", "-o", $out, "-w", "%{http_code}", "-X", "POST", "-H", "Authorization: Bearer $Token", "-F", "file=@$File")
    foreach ($k in $Fields.Keys) { $a += @("-F", "$k=$($Fields[$k])") }
    $a += "$ApiUrl/documents/$DocId/revisions"
    $code = & curl.exe @a
    $data = $null
    try { $data = Get-Content $out -Raw | ConvertFrom-Json } catch {}
    return [pscustomobject]@{ Status = [int]$code; Data = $data }
}

# ---- 1. pytest ----
if (-not (Test-Path $py)) { throw "Python venv not found at $py. Run scripts\dev.ps1 first." }
Set-Location $api
if (-not $SkipPytest) {
    Step "Running pytest"
    & $py -m pytest -q
    if ($LASTEXITCODE -ne 0) { Write-Host "`npytest FAILED. Copy the output above and send it to Claude." -ForegroundColor Red; exit 1 }
}

# ---- 2. migrations + seed ----
Step "Applying database migrations and demo users"
$versions = Join-Path $api "alembic\versions"
if (-not (Get-ChildItem $versions -Filter "*.py" -ErrorAction SilentlyContinue)) {
    Write-Host "No migration yet: generating the initial one (dev database is reset)."
    Remove-Item (Join-Path $api "bimguard_dev.db") -ErrorAction SilentlyContinue
    & $py -m alembic revision --autogenerate -m "initial schema"
    if ($LASTEXITCODE -ne 0) { throw "Could not generate the migration." }
}
& $py -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { throw "Migration failed." }
& $py -m app.seed
if ($LASTEXITCODE -ne 0) { throw "Seeding failed." }

# ---- 3. servers ----
Step "Starting servers (if not already running)"
$apiUp = $false
try { Invoke-WebRequest -Uri "$ApiUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; $apiUp = $true } catch {}
if ($apiUp) { Write-Host "API already running." }
else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$api'; & '$py' -m uvicorn app.main:app --reload"
    if (-not (Wait-Url "$ApiUrl/health" 40)) { throw "API did not start. Check the API window for the error." }
    Write-Host "API started."
}
if (Test-Port 3000) { Write-Host "Web app already running." }
elseif (Test-Path (Join-Path $web "node_modules")) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$web'; npm.cmd run dev"
    Write-Host "Web app starting."
} else { Write-Host "Web app not installed. Run scripts\dev.ps1 once to install it." -ForegroundColor Yellow }

# ---- 4. demo flow through the API ----
Step "Demo flow: sign in as admin"
$login = Call "POST" "/auth/login" $null $null @{ username = "admin@example.local"; password = "admin-demo-pass" }
Check "Admin sign-in" ($login.Status -eq 200)
if ($login.Status -ne 200) { throw "Cannot sign in as admin. Did the seed step run against the same database?" }
$admin = $login.Data.access_token
$eng = (Call "POST" "/auth/login" $null $null @{ username = "engineer@example.local"; password = "engineer-demo-pass" }).Data.access_token

Step "Permissions"
$denied = Call "POST" "/projects" $eng @{ name = "Should not be created" }
Check "Engineer cannot create a project (403)" ($denied.Status -eq 403)

Step "Create project and document"
$stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
$p = Call "POST" "/projects" $admin @{ name = "Factory Expansion - Building A ($stamp)"; client = "Demo Client"; description = "Scripted M2 check" }
Check "Create project" ($p.Status -eq 201)
$pid1 = $p.Data.id
$d = Call "POST" "/projects/$pid1/documents" $eng @{ document_number = "A-101"; name = "Level 2 Floor Plan"; discipline = "architecture" }
Check "Add document A-101 (as engineer)" ($d.Status -eq 201)
$dup = Call "POST" "/projects/$pid1/documents" $eng @{ document_number = "A-101"; name = "Again"; discipline = "architecture" }
Check "Duplicate document number rejected (409)" ($dup.Status -eq 409)
$docId = $d.Data.id

Step "Upload two IFC revisions"
$tmp = Join-Path $env:TEMP ("bimguard_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
function New-Ifc($Path, $X) {
    $lines = @(
        "ISO-10303-21;", "HEADER;", "FILE_DESCRIPTION(('ViewDefinition [ReferenceView]'),'2;1');",
        "FILE_NAME('architecture.ifc','2026-10-07T09:00:00',('BIMGuard demo'),(''),'','','');",
        "FILE_SCHEMA(('IFC4'));", "ENDSEC;", "DATA;",
        "#1=IFCWALL('wall-204',`$,'Wall 204 X=$X m',`$,`$,`$,`$,`$,.STANDARD.);",
        "ENDSEC;", "END-ISO-10303-21;")
    Set-Content -Path $Path -Value $lines -Encoding ascii
}
$f1 = Join-Path $tmp "architecture_v1.ifc"; New-Ifc $f1 "10.0"
$f2 = Join-Path $tmp "architecture_v2.ifc"; New-Ifc $f2 "10.3"

$u1 = Upload $docId $eng $f1 @{ revision_number = "12"; status = "approved"; change_summary = "Baseline architecture model" }
Check "Upload v12 (placeholder IFC)" ($u1.Status -eq 201 -and $u1.Data.revision_number -eq 12)
$u2 = Upload $docId $eng $f2 @{ change_summary = "Wall 204 moved 300 mm" }
Check "Upload changed file -> v13 (auto number)" ($u2.Status -eq 201 -and $u2.Data.revision_number -eq 13)
$u3 = Upload $docId $eng $f2 @{ change_summary = "Same file again" }
Check "Identical file rejected as duplicate (409)" ($u3.Status -eq 409)
$bad = Join-Path $tmp "evil.exe"; Set-Content $bad "MZ" -Encoding ascii
$u4 = Upload $docId $eng $bad @{}
Check "Unsupported file type rejected (422)" ($u4.Status -eq 422)

Step "Revision history"
$revs = Call "GET" "/documents/$docId/revisions" $admin
$revs.Data | ForEach-Object { "  v{0,-3} {1,-11} {2}  {3}" -f $_.revision_number, $_.status, $_.original_filename, $_.change_summary }
Check "v12 is superseded after v13 upload" (($revs.Data | Where-Object { $_.revision_number -eq 12 }).status -eq "superseded")

Step "Audit log"
$audit = Call "GET" "/audit-logs?project_id=$pid1" $admin
Write-Host ("  {0} audit events recorded for this project" -f $audit.Data.total)
Check "Audit trail contains revision events" (($audit.Data.items | Where-Object { $_.action -eq "revision.created" }).Count -ge 2)

Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

# ---- 5. result ----
$projectUrl = "http://localhost:3000/projects/$pid1"
Write-Host ""
if ($script:fails -eq 0) { Write-Host "ALL CHECKS PASSED" -ForegroundColor Green }
else { Write-Host "$($script:fails) CHECK(S) FAILED. Copy the output above and send it to Claude." -ForegroundColor Red }
Write-Host "Project created for you to inspect: $projectUrl"
Write-Host "Sign in with admin@example.local / admin-demo-pass, then click History on A-101."
if (-not $NoBrowser -and (Wait-Url "http://localhost:3000" 30)) { Start-Process $projectUrl }
