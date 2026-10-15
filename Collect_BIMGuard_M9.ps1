$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path

if (!(Test-Path (Join-Path $root 'app'))) {
    throw "Run this script from the BIMGuard repository root (the folder containing 'app'). Current directory: $root"
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$outDir = Join-Path $root "bimguard-m9-diagnostics-$stamp"
$stage = Join-Path $env:TEMP "bimguard-m9-stage-$stamp"
$testLog = Join-Path $stage 'm9-test-output.txt'
$summary = Join-Path $stage 'diagnostic-summary.txt'
$zipPath = Join-Path $root "bimguard-m9-diagnostics-$stamp.zip"

New-Item -ItemType Directory -Path $stage -Force | Out-Null

Write-Host "=== BIMGuard Milestone 9: targeted tests ===" -ForegroundColor Cyan
Write-Host "Repository: $root"
Write-Host "Running: py -m pytest tests/test_ai_api.py tests/test_ai_provider.py -vv --tb=long"

$testExit = 999
try {
    & py -m pytest tests/test_ai_api.py tests/test_ai_provider.py -vv --tb=long 2>&1 |
        Tee-Object -FilePath $testLog
    $testExit = $LASTEXITCODE
}
catch {
    $_ | Out-String | Add-Content -Path $testLog
    Write-Host "Test invocation raised an error: $($_.Exception.Message)" -ForegroundColor Red
}

# Collect Python application sources, migration sources, the targeted tests,
# test fixtures, and project dependency/test configuration. Never collect .env files,
# databases, virtual environments, node_modules, Git internals, or credentials.
$filesToCopy = New-Object System.Collections.Generic.List[string]

foreach ($dirName in @('app', 'alembic', 'migrations')) {
    $dirPath = Join-Path $root $dirName
    if (Test-Path $dirPath) {
        Get-ChildItem $dirPath -Recurse -File -Filter '*.py' |
            Where-Object { $_.FullName -notmatch '[\\/](__pycache__|\.venv|venv|node_modules|\.git)[\\/]' } |
            ForEach-Object { $filesToCopy.Add($_.FullName) }
    }
}

# Include common Next.js frontend locations needed for the remaining M9 UI work.
$frontendExtensions = @('.ts','.tsx','.js','.jsx','.css','.json','.md','.mjs','.cjs')
$frontendDirs = @('frontend','web','client','ui','apps/web')
foreach ($dirName in $frontendDirs) {
    $dirPath = Join-Path $root $dirName
    if (Test-Path $dirPath) {
        Get-ChildItem $dirPath -Recurse -File |
            Where-Object {
                $frontendExtensions -contains $_.Extension.ToLowerInvariant() -and
                $_.FullName -notmatch '[\\/](__pycache__|\.venv|venv|node_modules|\.git|\.next|out|dist|build)[\\/]'
            } |
            ForEach-Object { $filesToCopy.Add($_.FullName) }
    }
}

$selectedTestNames = @('test_ai_core.py', 'test_ai_api.py', 'test_ai_provider.py', 'conftest.py')
$testsDir = Join-Path $root 'tests'
if (Test-Path $testsDir) {
    Get-ChildItem $testsDir -Recurse -File -Filter '*.py' |
        Where-Object {
            ($selectedTestNames -contains $_.Name -or $_.FullName -match '[\\/]fixtures[\\/]') -and
            $_.FullName -notmatch '[\\/](__pycache__|\.venv|venv|node_modules|\.git)[\\/]'
        } |
        ForEach-Object { $filesToCopy.Add($_.FullName) }
}

$configNames = @('alembic.ini','pyproject.toml','pytest.ini','tox.ini','setup.cfg','requirements.txt','requirements-dev.txt','requirements-dev.in','requirements.in','setup.py','package.json','tsconfig.json','next.config.js','next.config.mjs','next.config.ts','tailwind.config.js','tailwind.config.ts','postcss.config.js','components.json')
foreach ($name in $configNames) {
    $p = Join-Path $root $name
    if (Test-Path $p -PathType Leaf) { $filesToCopy.Add($p) }
}

# Capture a few safe repository facts (no environment variables or .env contents).
$statusLines = @()
try {
    $statusLines = @(& git -C $root status --short 2>&1)
} catch { $statusLines = @('git status unavailable') }

$summaryText = @(
    "BIMGuard M9 diagnostics",
    "Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')",
    "Repository: $root",
    "Targeted pytest exit code: $testExit",
    "Tests run: tests/test_ai_api.py tests/test_ai_provider.py",
    "",
    "Git status --short:",
    ($statusLines -join "`r`n"),
    "",
    "Files included:"
) + @($filesToCopy | ForEach-Object { $_.Substring($root.Length).TrimStart('\','/') } | Sort-Object -Unique)
$summaryText | Set-Content -Path $summary -Encoding UTF8

foreach ($src in ($filesToCopy | Sort-Object -Unique)) {
    $relative = $src.Substring($root.Length).TrimStart('\','/')
    if ($relative -match '(^|[\\/])\.env([^\\/]*$|[\\/])' -or $relative -match '\.(db|sqlite|sqlite3)$') { continue }
    $dest = Join-Path $stage $relative
    $destDir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest -Force
}

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -Force

Write-Host "`n=== RESULT ===" -ForegroundColor Cyan
Write-Host "Targeted test exit code: $testExit"
Write-Host "Diagnostic package: $zipPath" -ForegroundColor Green
if ($testExit -eq 0) {
    Write-Host 'Both targeted test files passed.' -ForegroundColor Green
} else {
    Write-Host 'Tests failed or could not start. The full output is included in the ZIP.' -ForegroundColor Yellow
}
Write-Host 'No application source files were modified by this diagnostic script.'
Write-Host 'Upload the ZIP here so the failures can be fixed against the actual source.'

Remove-Item -LiteralPath $stage -Recurse -Force
