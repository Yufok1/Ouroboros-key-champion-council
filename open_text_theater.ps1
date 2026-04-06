$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$stateDir = Join-Path $root "data"
$statePath = Join-Path $stateDir "text_theater_window.json"

if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}

if (Test-Path $statePath) {
    try {
        $state = Get-Content $statePath -Raw | ConvertFrom-Json
        if ($state -and $state.pid) {
            $existing = Get-Process -Id ([int]$state.pid) -ErrorAction SilentlyContinue
            if ($existing) {
                Write-Host "Text Theater already running (PID $($state.pid))."
                exit 0
            }
        }
    } catch {
    }
    Remove-Item $statePath -ErrorAction SilentlyContinue
}

$psExe = (Get-Process -Id $PID).Path
if (-not $psExe) { $psExe = "powershell.exe" }

$launcher = Join-Path $root "run_text_theater.ps1"
$argList = @(
    "-NoLogo"
    "-ExecutionPolicy", "Bypass"
    "-File", ('"' + $launcher + '"')
)

$proc = Start-Process -FilePath $psExe -ArgumentList $argList -WorkingDirectory $root -PassThru

$state = [ordered]@{
    pid = $proc.Id
    started_ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
    launcher = $launcher
}
$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8

Write-Host "Opened Text Theater (PID $($proc.Id))."
