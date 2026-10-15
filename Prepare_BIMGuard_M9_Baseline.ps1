$ErrorActionPreference = 'Stop'
$root = (Get-Location).Path

if (!(Test-Path (Join-Path $root 'app')) -and !(Test-Path (Join-Path $root 'pyproject.toml'))) {
    throw "Run this from the BIMGuard repository root (expected an 'app' directory or pyproject.toml). Current directory: $root"
}

$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$stage = Join-Path $env:TEMP "bimguard-m9-baseline-$stamp"
$zipPath = Join-Path $root "bimguard-m9-baseline-$stamp.zip"
New-Item -ItemType Directory -Path $stage -Force | Out-Null

$skipPattern = '[\\/](\.git|\.venv|venv|env|node_modules|\.next|__pycache__|\.pytest_cache|\.mypy_cache|\.ruff_cache|dist|build|coverage|\.tox|\.idea|\.vscode)[\\/]'
$files = New-Object System.Collections.Generic.List[string]

# Python source, tests, migrations, and relevant Markdown documentation.
foreach ($dirName in @('app','backend','server','tests','alembic','migrations','docs','scripts')) {
    $dir = Join-Path $root $dirName
    if (Test-Path $dir -PathType Container) {
        Get-ChildItem $dir -Recurse -File | Where-Object {
            $_.FullName -notmatch $skipPattern -and
            $_.FullName -notmatch '[\\/]\.env[^\\/]*$' -and
            ($_.Extension -in @('.py','.md','.toml','.ini','.cfg','.sql','.json','.yml','.yaml','.txt','.ps1'))
        } | ForEach-Object { $files.Add($_.FullName) }
    }
}

# Frontend sources and configuration, whichever common folder name the repo uses.
$frontendDirs = @('frontend','web','client','ui','apps/web')
$frontendExt = @('.ts','.tsx','.js','.jsx','.css','.json','.md','.mjs','.cjs','.html','.svg')
foreach ($dirName in $frontendDirs) {
    $dir = Join-Path $root $dirName
    if (Test-Path $dir -PathType Container) {
        Get-ChildItem $dir -Recurse -File | Where-Object {
            $_.FullName -notmatch $skipPattern -and
            $_.FullName -notmatch '[\\/]\.env[^\\/]*$' -and
            $frontendExt -contains $_.Extension.ToLowerInvariant()
        } | ForEach-Object { $files.Add($_.FullName) }
    }
}

# Root project/config files. Explicitly exclude all .env files and database files.
$rootNames = @(
    'README.md','pyproject.toml','pytest.ini','tox.ini','setup.cfg','setup.py',
    'alembic.ini','requirements.txt','requirements-dev.txt','requirements-dev.in',
    'requirements.in','Pipfile','Pipfile.lock','poetry.lock','uv.lock','Dockerfile',
    'docker-compose.yml','compose.yml','package.json','package-lock.json','pnpm-lock.yaml',
    'yarn.lock','tsconfig.json','next.config.js','next.config.mjs','next.config.ts',
    'tailwind.config.js','tailwind.config.ts','postcss.config.js','components.json',
    'Makefile','.gitignore'
)
foreach ($name in $rootNames) {
    $p = Join-Path $root $name
    if (Test-Path $p -PathType Leaf) { $files.Add($p) }
}

# Include safe repository diagnostics: tree, current branch, status, and recent commits.
$metaDir = Join-Path $stage '_repository_metadata'
New-Item -ItemType Directory -Path $metaDir -Force | Out-Null
$meta = New-Object System.Collections.Generic.List[string]
$meta.Add("Repository root: $root")
$meta.Add("Created: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')")
$meta.Add('')
$meta.Add('=== Git branch ===')
try { $meta.AddRange([string[]]@(& git -C $root branch --show-current 2>&1)) } catch { $meta.Add('git unavailable') }
$meta.Add('')
$meta.Add('=== Git status --short ===')
try { $meta.AddRange([string[]]@(& git -C $root status --short 2>&1)) } catch { $meta.Add('git status unavailable') }
$meta.Add('')
$meta.Add('=== Recent commits ===')
try { $meta.AddRange([string[]]@(& git -C $root log -5 --oneline 2>&1)) } catch { $meta.Add('git log unavailable') }
$meta.Add('')
$meta.Add('=== Files included ===')
$uniqueFiles = @($files | Sort-Object -Unique)
foreach ($src in $uniqueFiles) { $meta.Add($src.Substring($root.Length).TrimStart('\','/')) }
$meta | Set-Content -LiteralPath (Join-Path $metaDir 'repository-summary.txt') -Encoding UTF8

foreach ($src in $uniqueFiles) {
    $relative = $src.Substring($root.Length).TrimStart('\','/')
    if ($relative -match '(^|[\\/])\.env[^\\/]*$') { continue }
    if ($relative -match '\.(db|sqlite|sqlite3|pyc)$') { continue }
    $dest = Join-Path $stage $relative
    $destDir = Split-Path $dest -Parent
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest -Force
}

Compress-Archive -Path (Join-Path $stage '*') -DestinationPath $zipPath -Force
Remove-Item -LiteralPath $stage -Recurse -Force

Write-Host "`nBIMGuard M9 baseline package created:" -ForegroundColor Green
Write-Host $zipPath -ForegroundColor Cyan
Write-Host "Included source/config files: $($uniqueFiles.Count)"
Write-Host 'No app source files were modified. .env files, local DBs, virtual environments, caches, node_modules and .git were excluded.'
