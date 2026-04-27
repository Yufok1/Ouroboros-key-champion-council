[CmdletBinding()]
param(
    [string]$Source = $PSScriptRoot,
    [string[]]$Destinations = @(
        "D:\workspace-backups\champion_councl",
        "G:\champion_councl"
    ),
    [switch]$Watch,
    [int]$IntervalSeconds = 300,
    [switch]$Mirror,
    [switch]$WhatIfSync
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Stamp {
    param(
        [string]$Message,
        [ConsoleColor]$Color = [ConsoleColor]::Gray
    )

    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Write-Host "[$stamp] $Message" -ForegroundColor $Color
}

function Test-BackupDestination {
    param([string]$Destination)

    $root = Split-Path -Path $Destination -Qualifier
    if ([string]::IsNullOrWhiteSpace($root)) {
        return [pscustomobject]@{
            Ready = $false
            Root = ""
            Reason = "No drive root found in destination path."
        }
    }

    if (-not (Test-Path -LiteralPath $root)) {
        return [pscustomobject]@{
            Ready = $false
            Root = $root
            Reason = "Drive $root is not currently mounted."
        }
    }

    return [pscustomobject]@{
        Ready = $true
        Root = $root
        Reason = ""
    }
}

function Invoke-BackupSync {
    param(
        [string]$ResolvedSource,
        [string]$Destination,
        [bool]$UseMirror,
        [bool]$PreviewOnly
    )

    $destState = Test-BackupDestination -Destination $Destination
    if (-not $destState.Ready) {
        Write-Stamp "Skipping $Destination - $($destState.Reason)" Yellow
        return [pscustomobject]@{
            Destination = $Destination
            Status = "skipped"
            ExitCode = $null
            Reason = $destState.Reason
        }
    }

    if (-not $PreviewOnly -and -not (Test-Path -LiteralPath $Destination)) {
        New-Item -ItemType Directory -Path $Destination -Force | Out-Null
    }

    $modeLabel = if ($UseMirror) { "mirror" } else { "additive" }
    $roboArgs = @(
        $ResolvedSource
        $Destination
        $(if ($UseMirror) { "/MIR" } else { "/E" })
        "/COPY:DAT"
        "/DCOPY:DAT"
        "/R:2"
        "/W:2"
        "/Z"
        "/FFT"
        "/XJ"
        "/XO"
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
        return [pscustomobject]@{
            Destination = $Destination
            Status = "preview"
            ExitCode = 0
            Reason = ""
        }
    }

    Write-Stamp "Syncing ($modeLabel): $ResolvedSource -> $Destination" Cyan
    & robocopy @roboArgs | Out-Null
    $exitCode = $LASTEXITCODE

    if ($exitCode -lt 8) {
        Write-Stamp "Backup OK for $Destination (robocopy exit $exitCode)" Green
        return [pscustomobject]@{
            Destination = $Destination
            Status = "ok"
            ExitCode = $exitCode
            Reason = ""
        }
    }

    Write-Stamp "Backup FAILED for $Destination (robocopy exit $exitCode)" Red
    return [pscustomobject]@{
        Destination = $Destination
        Status = "failed"
        ExitCode = $exitCode
        Reason = "robocopy exit $exitCode"
    }
}

$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
Write-Stamp "Source: $resolvedSource" White
Write-Stamp ("Destinations: " + ($Destinations -join ", ")) White
Write-Stamp ("Mode: " + $(if ($Mirror) { "mirror" } else { "additive sync" })) White

if ($Watch) {
    $IntervalSeconds = [Math]::Max(15, $IntervalSeconds)
    Write-Stamp "Watch mode enabled. Re-sync interval: $IntervalSeconds seconds." White
    Write-Stamp "If G: drops out, the script will keep syncing D: and retry G: on the next pass." White
}

do {
    $results = foreach ($destination in $Destinations) {
        Invoke-BackupSync -ResolvedSource $resolvedSource -Destination $destination -UseMirror:$Mirror -PreviewOnly:$WhatIfSync
    }

    $failed = @($results | Where-Object { $_.Status -eq "failed" })
    if ($failed.Count -gt 0 -and -not $Watch) {
        throw ("Backup failed for: " + (($failed | ForEach-Object { $_.Destination }) -join ", "))
    }

    if (-not $Watch) {
        break
    }

    Start-Sleep -Seconds $IntervalSeconds
} while ($true)
