$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$statePath = Join-Path (Join-Path $root "data") "text_theater_window.json"

if (-not (Test-Path $statePath)) {
    Write-Host "No tracked Text Theater window."
    exit 0
}

try {
    $state = Get-Content $statePath -Raw | ConvertFrom-Json
} catch {
    Remove-Item $statePath -ErrorAction SilentlyContinue
    Write-Host "Text Theater state was invalid and has been cleared."
    exit 0
}

$pid = [int]($state.pid)
if ($pid -gt 0) {
    $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
    if ($proc) {
        Stop-Process -Id $pid -Force
        Write-Host "Closed Text Theater (PID $pid)."
    } else {
        Write-Host "Text Theater PID $pid is not running."
    }
}

Remove-Item $statePath -ErrorAction SilentlyContinue
