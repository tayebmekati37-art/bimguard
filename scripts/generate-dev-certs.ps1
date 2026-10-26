<#
 Generate a self-signed TLS certificate for local testing of the reverse
 proxy. Not for production. For production, use mkcert or a real CA
 (Let's Encrypt via Caddy's automatic mode, or your company's CA).

 Writes to deploy/nginx/certs/ and deploy/caddy/certs/ so both proxy
 options work with the same certificate.

 Usage:
   scripts\generate-dev-certs.ps1
   scripts\generate-dev-certs.ps1 -Days 90
#>
param(
    [int]$Days = 365
)
$ErrorActionPreference = "Stop"

$openssl = Get-Command openssl -ErrorAction SilentlyContinue
if (-not $openssl) {
    Write-Host "[FAIL] openssl not found in PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Install one of:"
    Write-Host "  - Chocolatey:    choco install openssl"
    Write-Host "  - Scoop:         scoop install openssl"
    Write-Host "  - Git for Windows ships openssl at: C:\Program Files\Git\usr\bin\openssl.exe"
    Write-Host "    (add that dir to PATH, or run the command from Git Bash)"
    Write-Host "  - Or use mkcert: https://github.com/FiloSottile/mkcert"
    Write-Host ""
    Write-Host "Alternative without openssl: use mkcert, which auto-trusts the cert:"
    Write-Host "    mkcert -install"
    Write-Host "    mkcert -cert-file deploy\nginx\certs\server.crt -key-file deploy\nginx\certs\server.key localhost 127.0.0.1"
    exit 1
}

$root = "C:\dev\bimguard"
$targets = @(
    (Join-Path $root "deploy\nginx\certs"),
    (Join-Path $root "deploy\caddy\certs")
)

$subj = "/CN=localhost"
$san  = "subjectAltName=DNS:localhost,DNS:bimguard.local,IP:127.0.0.1,IP:::1"

foreach ($dir in $targets) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    $crt = Join-Path $dir "server.crt"
    $key = Join-Path $dir "server.key"

    Write-Host "Generating cert for $dir..."
    $old = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & openssl req -x509 -nodes -days $Days -newkey rsa:2048 `
        -keyout $key -out $crt `
        -subj $subj -addext $san 2>&1 | Out-Null
    $code = $LASTEXITCODE
    $ErrorActionPreference = $old

    if ($code -ne 0 -or -not (Test-Path $crt) -or -not (Test-Path $key)) {
        Write-Host "[FAIL] openssl failed for $dir (exit $code)"
        exit 1
    }
    Write-Host ("  [ok] {0}" -f $crt)
    Write-Host ("  [ok] {0}" -f $key)
}

Write-Host ""
Write-Host "Self-signed cert valid for $Days days. Browsers will warn until"
Write-Host "you accept the cert once, or install the .crt in your trust store."
Write-Host ""
Write-Host "Next steps:"
Write-Host "  docker compose -f docker-compose.yml -f docker-compose.proxy-nginx.yml up -d"
Write-Host "  # or"
Write-Host "  docker compose -f docker-compose.yml -f docker-compose.proxy-caddy.yml up -d"
Write-Host ""
Write-Host "Then: https://localhost/health should return 200."