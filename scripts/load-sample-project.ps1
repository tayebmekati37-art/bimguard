<#
 Loads the synthetic "Factory Expansion - Building A" project through the API:
 five documents, each with its first model revision (A-101 v12, S-201 v8, M-301 v5, Q-101 v6, E-020 v3).
 The API must be running. Architecture v2 is NOT uploaded: that is the revision you upload during the demo.
 Run: powershell -ExecutionPolicy Bypass -File C:\dev\bimguard\scripts\load-sample-project.ps1
#>
param([string]$ApiUrl = "http://localhost:8000", [switch]$WithArchitectureV2)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$ifc  = Join-Path $root "data\sample_ifc"
$json = Join-Path $root "data\sample_projects\factory_expansion"

function Call($Method, $Path, $Token, $Body, $Form) {
    $params = @{ Uri = "$ApiUrl$Path"; Method = $Method; UseBasicParsing = $true; Headers = @{} }
    if ($Token) { $params.Headers["Authorization"] = "Bearer $Token" }
    if ($Form) { $params.Body = $Form } elseif ($Body) { $params.Body = ($Body | ConvertTo-Json); $params.ContentType = "application/json" }
    try { (Invoke-WebRequest @params).Content | ConvertFrom-Json }
    catch { throw "API call $Method $Path failed: $($_.ErrorDetails.Message)" }
}
function Upload($DocId, $Token, $File, $Revision, $Summary, $Status = "approved") {
    $out = Join-Path $env:TEMP "bimguard_sample_upload.json"
    $code = & curl.exe -s -o $out -w "%{http_code}" -X POST -H "Authorization: Bearer $Token" `
        -F "file=@$File" -F "revision_number=$Revision" -F "status=$Status" -F "change_summary=$Summary" "$ApiUrl/documents/$DocId/revisions"
    if ($code -ne "201") { throw "Upload of $File failed ($code): $(Get-Content $out -Raw)" }
}

try { Invoke-WebRequest "$ApiUrl/health" -UseBasicParsing | Out-Null } catch { throw "The API is not running at $ApiUrl. Start it first (scripts\start.ps1)." }
$token = (Call "POST" "/auth/login" $null $null @{ username = "admin@example.local"; password = "admin-demo-pass" }).access_token

$project = Call "POST" "/projects" $token @{
    name = "Factory Expansion - Building A"; client = "Sample Client (simulated)"
    description = "Synthetic demonstration project. All data is simulated." }
Write-Host "Created project $($project.name)"

$docs = @(
    @{ n = "A-101"; name = "Level 2 Floor Plan";       d = "architecture"; f = Join-Path $ifc "architecture_v1.ifc"; r = 12 },
    @{ n = "S-201"; name = "Level 2 Framing Plan";     d = "structure";    f = Join-Path $ifc "structure_v1.ifc";    r = 8 },
    @{ n = "M-301"; name = "Level 2 HVAC Layout";      d = "mep";          f = Join-Path $ifc "mep_v1.ifc";          r = 5 },
    @{ n = "Q-101"; name = "Level 2 Quantity Take-off"; d = "quantity";    f = Join-Path $json "quantity_v1.json";   r = 6 },
    @{ n = "E-020"; name = "Equipment Schedule";       d = "equipment";    f = Join-Path $json "equipment_v1.json";  r = 3 }
)
$ids = @{}
foreach ($doc in $docs) {
    $created = Call "POST" "/projects/$($project.id)/documents" $token @{ document_number = $doc.n; name = $doc.name; discipline = $doc.d }
    $ids[$doc.n] = $created.id
    Upload $created.id $token $doc.f $doc.r "Baseline sample revision"
    Write-Host ("  {0}  v{1}  {2}" -f $doc.n, $doc.r, (Split-Path $doc.f -Leaf))
}
if ($WithArchitectureV2) {
    Write-Host "Waiting for A-101 v12 to finish processing..."
    for ($i = 0; $i -lt 30; $i++) {
        $rev = (Call "GET" "/documents/$($ids['A-101'])/revisions" $token) | Select-Object -First 1
        if ($rev.extraction_status -ne "pending") { break }
        Start-Sleep -Seconds 1
    }
    Upload $ids["A-101"] $token (Join-Path $ifc "architecture_v2.ifc") 13 "Wall W-204 moved 300 mm, door D-202A relocated, room 204 parameters changed, wall W-207 added" "in_review"
    Write-Host "  A-101  v13  architecture_v2.ifc  (changes are detected automatically)"
}
Write-Host "`nDone. Open http://localhost:3000/projects/$($project.id)"
Write-Host "Click History on a document: the Model data column shows the extracted elements."
