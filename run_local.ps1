$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $env:WEB_HOST) { $env:WEB_HOST = "127.0.0.1" }
if (-not $env:WEB_PORT) { $env:WEB_PORT = "7866" }
if (-not $env:MCP_PORT) { $env:MCP_PORT = "8766" }
if (-not $env:APP_MODE) { $env:APP_MODE = "development" }
if (-not $env:MCP_EXTERNAL_POLICY) { $env:MCP_EXTERNAL_POLICY = "full" }
if (-not $env:PERSISTENCE_MODE) { $env:PERSISTENCE_MODE = "local" }
if (-not $env:PERSISTENCE_DATA_DIR) { $env:PERSISTENCE_DATA_DIR = (Join-Path $root "data\champion-council-state") }
if (-not $env:AUTOSAVE_INTERVAL) { $env:AUTOSAVE_INTERVAL = "60" }
if (-not $env:PYTHONNOUSERSITE) { $env:PYTHONNOUSERSITE = "1" }

Write-Host "[local] WEB_HOST=$env:WEB_HOST WEB_PORT=$env:WEB_PORT MCP_PORT=$env:MCP_PORT"
Write-Host "[local] APP_MODE=$env:APP_MODE MCP_EXTERNAL_POLICY=$env:MCP_EXTERNAL_POLICY"
Write-Host "[local] PERSISTENCE_MODE=$env:PERSISTENCE_MODE PERSISTENCE_DATA_DIR=$env:PERSISTENCE_DATA_DIR"
Write-Host "[local] PYTHONNOUSERSITE=$env:PYTHONNOUSERSITE"

python server.py
