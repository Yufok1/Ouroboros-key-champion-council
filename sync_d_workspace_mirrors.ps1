[CmdletBinding()]
param(
    [string]$Source = "D:\End-Game\champion_councl",
    [string[]]$Destinations = @(
        "F:\End-Game\champion_councl",
        "G:\champion_councl"
    ),
    [switch]$Watch,
    [int]$IntervalSeconds = 60,
    [switch]$Additive,
    [switch]$WhatIfSync,
    [string]$LogPath = "D:\workspace-backups\mirror-logs\sync_d_workspace_mirrors.log"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Stamp {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$stamp] $Message"
    Write-Host $line -ForegroundColor $Color
    if (-not [string]::IsNullOrWhiteSpace($LogPath)) {
        $logDir = Split-Path -Path $LogPath -Parent
        if (-not [string]::IsNullOrWhiteSpace($logDir) -and -not (Test-Path -LiteralPath $logDir)) {
            New-Item -ItemType Directory -Path $logDir -Force | Out-Null
        }
        Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
    }
}

function Test-DestinationRoot {
    param([string]$Destination)

    $root = Split-Path -Path $Destination -Qualifier
    if ([string]::IsNullOrWhiteSpace($root)) {
        return [pscustomobject]@{ Ready = $false; Reason = "No drive root found." }
    }
    if (-not (Test-Path -LiteralPath $root)) {
        return [pscustomobject]@{ Ready = $false; Reason = "Drive $root is not mounted." }
    }
    return [pscustomobject]@{ Ready = $true; Reason = "" }
}

function Invoke-MirrorSync {
    param(
        [string]$ResolvedSource,
        [string]$Destination,
        [bool]$UseAdditive,
        [bool]$PreviewOnly
    )

    $destState = Test-DestinationRoot -Destination $Destination
    if (-not $destState.Ready) {
        Write-Stamp "Skipping $Destination - $($destState.Reason)" Yellow
        return [pscustomobject]@{ Destination = $Destination; Status = "skipped"; ExitCode = $null }
    }

    if (-not $PreviewOnly -and -not (Test-Path -LiteralPath $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }

    $modeArg = if ($UseAdditive) { "/E" } else { "/MIR" }
    $modeLabel = if ($UseAdditive) { "additive" } else { "mirror" }
    $roboArgs = @(
        $ResolvedSource
        $Destination
        $modeArg
        "/COPY:DAT"
        "/DCOPY:DAT"
        "/R:1"
        "/W:2"
        "/Z"
        "/FFT"
        "/XJ"
        "/NP"
        "/NFL"
        "/NDL"
        "/NJH"
        "/NJS"
    )

    if ($PreviewOnly) {
        Write-Stamp "WhatIf $modeLabel sync: $ResolvedSource -> $Destination" Cyan
        Write-Host ("robocopy " + ($roboArgs | ForEach-Object {
            if ($_ -match "\s") { '"' + $_ + '"' } else { $_ }
        }) -join " ")
        return [pscustomobject]@{ Destination = $Destination; Status = "preview"; ExitCode = 0 }
    }

    Write-Stamp "Syncing ($modeLabel): $ResolvedSource -> $Destination" Cyan
    & robocopy @roboArgs | Out-Null
    $exitCode = $LASTEXITCODE

    if ($exitCode -lt 8) {
        Write-Stamp "Mirror OK for $Destination (robocopy exit $exitCode)" Green
        return [pscustomobject]@{ Destination = $Destination; Status = "ok"; ExitCode = $exitCode }
    }

    Write-Stamp "Mirror FAILED for $Destination (robocopy exit $exitCode)" Red
    return [pscustomobject]@{ Destination = $Destination; Status = "failed"; ExitCode = $exitCode }
}

$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
if (-not (Test-Path -LiteralPath $resolvedSource)) {
    throw "Source workspace not found: $resolvedSource"
}

Write-Stamp "Source: $resolvedSource" White
Write-Stamp ("Destinations: " + ($Destinations -join ", ")) White
Write-Stamp ("Mode: " + $(if ($Additive) { "additive sync" } else { "exact mirror" })) White

if ($Watch) {
    $IntervalSeconds = [Math]::Max(15, $IntervalSeconds)
    Write-Stamp "Watch mode enabled. Re-sync interval: $IntervalSeconds seconds." White
    Write-Stamp "Missing USB drives are skipped and retried on the next pass." White
}

do {
    $results = foreach ($destination in $Destinations) {
        Invoke-MirrorSync -ResolvedSource $resolvedSource -Destination $destination -UseAdditive:$Additive -PreviewOnly:$WhatIfSync
    }

    $failed = @($results | Where-Object { $_.Status -eq "failed" })
    if ($failed.Count -gt 0 -and -not $Watch) {
        throw ("Mirror failed for: " + (($failed | ForEach-Object { $_.Destination }) -join ", "))
    }

    if (-not $Watch) {
        break
    }

    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
