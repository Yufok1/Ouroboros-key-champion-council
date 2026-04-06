$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $env:WEB_HOST) { $env:WEB_HOST = "127.0.0.1" }
if (-not $env:WEB_PORT) { $env:WEB_PORT = "7866" }

python scripts/text_theater.py @args
