$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[run] Virtualenv not found. Running setup first..."
    & "$PSScriptRoot\setup.ps1"
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
Write-Host "[run] Starting self_deploy backend..."
& $Python backend/server.py
