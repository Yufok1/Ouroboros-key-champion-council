$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$stateDir = Join-Path $root "data"
$statePath = Join-Path $stateDir "text_theater_window.json"
$wtProfileName = "Champion Council Text Theater"
$launcher = Join-Path $root "run_text_theater.ps1"

function Normalize-PathString {
    param(
        [string]$PathText
    )

    if ([string]::IsNullOrWhiteSpace($PathText)) {
        return ""
    }

    $expanded = [Environment]::ExpandEnvironmentVariables($PathText.Trim().Trim('"'))
    try {
        return [System.IO.Path]::GetFullPath($expanded).TrimEnd('\')
    } catch {
        return $expanded.TrimEnd('\')
    }
}

function Get-ProfileLauncherPath {
    param(
        [string]$CommandLine
    )

    if ([string]::IsNullOrWhiteSpace($CommandLine)) {
        return ""
    }

    if ($CommandLine -match '(?i)-File\s+"([^"]+)"') {
        return $matches[1]
    }
    if ($CommandLine -match "(?i)-File\s+'([^']+)'") {
        return $matches[1]
    }
    if ($CommandLine -match '(?i)-File\s+(\S+)') {
        return $matches[1]
    }

    return ""
}

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

$wtExe = Get-Command "wt.exe" -ErrorAction SilentlyContinue
$wtSettingsPaths = @(
    (Join-Path $env:LOCALAPPDATA "Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"),
    (Join-Path $env:LOCALAPPDATA "Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json"),
    (Join-Path $env:LOCALAPPDATA "Microsoft\Windows Terminal\settings.json")
)
$useWtProfile = $false
$wtProfileMismatch = ""
$normalizedRoot = Normalize-PathString $root
$normalizedLauncher = Normalize-PathString $launcher

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
            $profile = $profiles | Where-Object { $_.name -eq $wtProfileName } | Select-Object -First 1
            if (-not $profile) {
                continue
            }

            $profileLauncher = Normalize-PathString (Get-ProfileLauncherPath ([string]$profile.commandline))
            $profileStartDir = Normalize-PathString ([string]$profile.startingDirectory)
            $mismatchReasons = @()

            if ($profileLauncher -and $profileLauncher -ne $normalizedLauncher) {
                $mismatchReasons += "commandline=$profileLauncher"
            }
            if ($profileStartDir -and $profileStartDir -ne $normalizedRoot) {
                $mismatchReasons += "startingDirectory=$profileStartDir"
            }

            if ($mismatchReasons.Count -eq 0) {
                $useWtProfile = $true
            } else {
                $wtProfileMismatch = ($mismatchReasons -join "; ")
            }
            break
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
    if ($wtProfileMismatch) {
        Write-Host "Ignoring stale Windows Terminal profile '$wtProfileName' ($wtProfileMismatch)." -ForegroundColor Yellow
    }
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
