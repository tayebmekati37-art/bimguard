param([string]$ApiUrl = "http://localhost:8000")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$api  = Join-Path $root "apps\api"
$py   = Join-Path $api ".venv\Scripts\python.exe"
$ifc  = Join-Path $root "data\sample_ifc"
$json = Join-Path $root "data\sample_projects\factory_expansion"

function Call($Method, $Path, $Token, $Body, $Form) {
    $params = @{ Uri = "$ApiUrl$Path"; Method = $Method; UseBasicParsing = $true; Headers = @{} }
    if ($Token) { $params.Headers["Authorization"] = "Bearer $Token" }
    if ($Form) { $params.Body = $Form } elseif ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = "application/json" }
    try { (Invoke-WebRequest @params).Content | ConvertFrom-Json }
    catch { throw "API call $Method $Path failed: $($_.ErrorDetails.Message)" }
}
function Upload($DocId, $Token, $File, $Revision) {
    $out = Join-Path $env:TEMP "bimguard_verify_upload.json"
    $code = & curl.exe -s -o $out -w "%{http_code}" -X POST -H "Authorization: Bearer $Token" `
        -F "file=@$File" -F "revision_number=$Revision" -F "status=approved" -F "change_summary=Baseline sample revision" "$ApiUrl/documents/$DocId/revisions"
    if ($code -ne "201") { throw "Upload of $File failed ($code): $(Get-Content $out -Raw)" }
}

$docs = @(
    @{ n = "A-101"; name = "Level 2 Floor Plan";        d = "architecture"; f = (Join-Path $ifc "architecture_v1.ifc"); r = 12; expect = 19 },
    @{ n = "S-201"; name = "Level 2 Framing Plan";      d = "structure";    f = (Join-Path $ifc "structure_v1.ifc");    r = 8;  expect = 21 },
    @{ n = "M-301"; name = "Level 2 HVAC Layout";       d = "mep";          f = (Join-Path $ifc "mep_v1.ifc");          r = 5;  expect = 6 },
    @{ n = "Q-101"; name = "Level 2 Quantity Take-off"; d = "quantity";     f = (Join-Path $json "quantity_v1.json");   r = 6;  expect = 6 },
    @{ n = "E-020"; name = "Equipment Schedule";        d = "equipment";    f = (Join-Path $json "equipment_v1.json");  r = 3;  expect = 3 }
)
foreach ($doc in $docs) { if (-not (Test-Path $doc.f)) { throw "Sample file missing: $($doc.f). Re-copy the Milestone 3 files (data folder)." } }

# 1. API
$up = $false
try { Invoke-WebRequest "$ApiUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; $up = $true } catch {}
if (-not $up) {
    Write-Host "Starting the API..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$api'; & '$py' -m alembic upgrade head; & '$py' -m app.seed; & '$py' -m uvicorn app.main:app --reload"
    for ($i = 0; $i -lt 40 -and -not $up; $i++) {
        Start-Sleep -Seconds 1
        try { Invoke-WebRequest "$ApiUrl/health" -UseBasicParsing -TimeoutSec 2 | Out-Null; $up = $true } catch {}
    }
    if (-not $up) { throw "The API did not start. Check the API window for the error." }
}

# 2. Create project and upload
$token = (Call "POST" "/auth/login" $null $null @{ username = "admin@example.local"; password = "admin-demo-pass" }).access_token
$stamp = Get-Date -Format "HH:mm"
$project = Call "POST" "/projects" $token @{ name = "Factory Expansion - Building A (check $stamp)"; client = "Sample Client (simulated)"; description = "Synthetic sample project" }
Write-Host "Created project: $($project.name)"
foreach ($doc in $docs) {
    $created = Call "POST" "/projects/$($project.id)/documents" $token @{ document_number = $doc.n; name = $doc.name; discipline = $doc.d }
    $doc.id = $created.id
    Upload $created.id $token $doc.f $doc.r
}

# 3. Wait for background extraction
Write-Host "Waiting for model extraction..."
$deadline = (Get-Date).AddSeconds(90)
do {
    Start-Sleep -Seconds 2
    $pending = 0
    foreach ($doc in $docs) {
        $revs = @(Call "GET" "/documents/$($doc.id)/revisions" $token)
        $doc.rev = $revs[0]
        if ($doc.rev.extraction_status -eq "pending") { $pending++ }
    }
} while ($pending -gt 0 -and (Get-Date) -lt $deadline)

# 4. Report
$failures = 0
$table = foreach ($doc in $docs) {
    $ok = ($doc.rev.extraction_status -eq "ok" -and $doc.rev.element_count -eq $doc.expect)
    if (-not $ok) { $failures++ }
    [pscustomobject]@{
        Document = $doc.n; Revision = "v$($doc.rev.revision_number)"; Status = $doc.rev.extraction_status
        Elements = $doc.rev.element_count; Expected = $doc.expect; Result = $(if ($ok) { "PASS" } else { "FAIL" })
        Message = $doc.rev.extraction_message
    }
}
$table | Format-Table -AutoSize -Wrap
$url = "http://localhost:3000/projects/$($project.id)"
if ($failures -eq 0) { Write-Host "ALL 5 DOCUMENTS EXTRACTED CORRECTLY" -ForegroundColor Green }
else { Write-Host "$failures document(s) failed. Copy the table above and send it to Claude." -ForegroundColor Red }
Write-Host "Project page: $url"
Start-Process $url
