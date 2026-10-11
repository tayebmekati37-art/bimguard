<#
 Walks the Factory Expansion demo from BLOCKED to READY through the API, the same steps an engineer would take:
   1. validate (shows what blocks the release)
   2. update Q-101 with quantities that match architecture v13 (quantity_v2.json, uploaded as Q-101 v7)
   3. mark every stale dependency as reviewed
   4. approve A-101 v13
   5. validate again
 Run after:  scripts\load-sample-project.ps1 -WithArchitectureV2
 Run:  powershell -ExecutionPolicy Bypass -File C:\dev\bimguard\scripts\resolve-demo.ps1
#>
param([string]$ApiUrl = "http://localhost:8000", [string]$ProjectName = "Factory Expansion - Building A")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$qto2 = Join-Path $root "data\sample_projects\factory_expansion\quantity_v2.json"

function Call($Method, $Path, $Token, $Body, $Form) {
    $params = @{ Uri = "$ApiUrl$Path"; Method = $Method; UseBasicParsing = $true; Headers = @{} }
    if ($Token) { $params.Headers["Authorization"] = "Bearer $Token" }
    if ($Form) { $params.Body = $Form } elseif ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = "application/json" }
    try { $r = Invoke-WebRequest @params; if ($r.Content) { $r.Content | ConvertFrom-Json } }
    catch { throw "API call $Method $Path failed: $($_.ErrorDetails.Message)" }
}
function Show-Run($run, $token, $title) {
    Write-Host "`n=== $title ===" -ForegroundColor Cyan
    $color = if ($run.status -eq "READY") { "Green" } elseif ($run.status -eq "BLOCKED") { "Red" } else { "Yellow" }
    Write-Host ("  Status: {0}   open: {1}   blocking: {2}" -f $run.status, $run.summary.open, $run.summary.blocking) -ForegroundColor $color
    $page = Call "GET" "/validation-runs/$($run.id)/issues?limit=100" $token
    foreach ($i in $page.items) { Write-Host ("  [{0}] {1}: {2}" -f $i.severity, $i.document_number, $i.message) }
}

try { Invoke-WebRequest "$ApiUrl/health" -UseBasicParsing | Out-Null } catch { throw "The API is not running at $ApiUrl. Start it first (scripts\start.ps1)." }
$token = (Call "POST" "/auth/login" $null $null @{ username = "admin@example.local"; password = "admin-demo-pass" }).access_token
$projects = Call "GET" "/projects?q=$([uri]::EscapeDataString($ProjectName))&limit=50" $token
$project = $projects.items | Select-Object -First 1
if (-not $project) { throw "No project named '$ProjectName'. Run load-sample-project.ps1 -WithArchitectureV2 first." }
Write-Host "Project: $($project.name)"
$docs = @{}
(Call "GET" "/projects/$($project.id)/documents?limit=200" $token).items | ForEach-Object { $docs[$_.document_number] = $_ }

Show-Run (Call "POST" "/projects/$($project.id)/validate" $token) $token "1. Before: validation"

Write-Host "`n2. Uploading updated quantities as Q-101 v7..."
$out = Join-Path $env:TEMP "bimguard_resolve_upload.json"
$code = & curl.exe -s -o $out -w "%{http_code}" -X POST -H "Authorization: Bearer $token" -F "file=@$qto2" -F "revision_number=7" -F "status=approved" `
    -F "change_summary=Quantities updated for A-101 v13" "$ApiUrl/documents/$($docs['Q-101'].id)/revisions"
if ($code -ne "201") { throw "Upload failed ($code): $(Get-Content $out -Raw)" }
for ($i = 0; $i -lt 30; $i++) {
    $rev = (Call "GET" "/documents/$($docs['Q-101'].id)/revisions" $token) | Select-Object -First 1
    if ($rev.extraction_status -ne "pending") { break }
    Start-Sleep -Seconds 1
}

Write-Host "3. Marking stale dependencies as reviewed..."
$stale = (Call "GET" "/projects/$($project.id)/dependencies?stale=true&limit=100" $token).items
foreach ($d in $stale) {
    Call "POST" "/dependencies/$($d.id)/validate" $token | Out-Null
    Write-Host ("   {0} reviewed against {1} v{2}" -f $d.source_number, $d.provider_number, $d.provider_current_revision)
}

Write-Host "4. Approving A-101's current revision..."
$a101 = (Call "GET" "/documents/$($docs['A-101'].id)/revisions" $token) | Select-Object -First 1
if ($a101.status -eq "in_review") {
    Call "PATCH" "/revisions/$($a101.id)/status" $token @{ status = "approved" } | Out-Null
    Write-Host "   A-101 v$($a101.revision_number) approved"
} else { Write-Host "   A-101 v$($a101.revision_number) is already $($a101.status)" }

Show-Run (Call "POST" "/projects/$($project.id)/validate" $token) $token "5. After: validation"
Write-Host "`nOpen http://localhost:3000/projects/$($project.id)/validation"
