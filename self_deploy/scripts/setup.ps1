param(
    [switch]$Full
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv")) {
    Write-Host "[setup] Creating virtualenv..."
    python -m venv .venv
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"

Write-Host "[setup] Upgrading pip..."
& $Python -m pip install --upgrade pip

if ($Full) {
    Write-Host "[setup] Installing full dependencies (server + capsule)..."
    & $Python -m pip install -r requirements.txt
} else {
    Write-Host "[setup] Installing server dependencies..."
    & $Python -m pip install -r requirements-server.txt
}

$EnvFile = Join-Path $Root "config\.env"
$EnvExample = Join-Path $Root "config\.env.example"
if (-not (Test-Path $EnvFile) -and (Test-Path $EnvExample)) {
    Copy-Item $EnvExample $EnvFile
    Write-Host "[setup] Created config/.env from .env.example"
}

Write-Host "[setup] Done."
