$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$stateDir = Join-Path $root "data"
$statePath = Join-Path $stateDir "text_theater_window.json"
$wtProfileName = "Champion Council Text Theater"

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
$wtExe = Get-Command "wt.exe" -ErrorAction SilentlyContinue
$wtSettingsPaths = @(
    (Join-Path $env:LOCALAPPDATA "Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"),
    (Join-Path $env:LOCALAPPDATA "Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Windows Terminal\settings.json")
)
$useWtProfile = $false

if ($wtExe) {
    foreach ($settingsPath in $wtSettingsPaths) {
        if (-not (Test-Path $settingsPath)) {
            continue
        }
        try {
            $settings = Get-Content $settingsPath -Raw | ConvertFrom-Json -Depth 16
            $profiles = @()
            if ($settings.profiles) {
                if ($settings.profiles.list) {
                    $profiles = @($settings.profiles.list)
                } elseif ($settings.profiles -is [System.Array]) {
                    $profiles = @($settings.profiles)
                }
            }
            if ($profiles | Where-Object { $_.name -eq $wtProfileName }) {
                $useWtProfile = $true
                break
            }
        } catch {
        }
    }
}

if ($useWtProfile) {
    $argList = @(
        "-p", ('"' + $wtProfileName + '"')
    )
    $proc = Start-Process -FilePath $wtExe.Source -ArgumentList $argList -WorkingDirectory $root -PassThru
} else {
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
        host = "powershell-process"
    }
    $state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8
}

Write-Host "Opened Text Theater (PID $($proc.Id))."
