[CmdletBinding()]
param(
    [string]$SourceRepo = $PSScriptRoot,
    [string]$PrimaryPath = "D:\End-Game\champion_councl",
    [string]$HotSnapshotRoot = "D:\workspace-backups\champion_councl-hot",
    [string]$SnapshotName = "",
    [switch]$RefreshOnly
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

function Get-HotSnapshotPath {
    param(
        [string]$Root,
        [string]$Name
    )

    if (-not (Test-Path -LiteralPath $Root)) {
        throw "Hot snapshot root not found: $Root"
    }

    if (-not [string]::IsNullOrWhiteSpace($Name)) {
        $candidate = Join-Path $Root $Name
        if (-not (Test-Path -LiteralPath $candidate)) {
            throw "Requested hot snapshot not found: $candidate"
        }
        return (Resolve-Path -LiteralPath $candidate).Path
    }

    $latest = Get-ChildItem -LiteralPath $Root -Directory | Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if (-not $latest) {
        throw "No snapshot directories found under $Root"
    }
    return $latest.FullName
}

function Copy-SnapshotOverlay {
    param(
        [string]$SnapshotPath,
        [string]$DestinationPath
    )

    $files = Get-ChildItem -LiteralPath $SnapshotPath -Recurse -File -Force |
        Where-Object { $_.FullName -notlike (Join-Path $SnapshotPath "_meta*") }

    foreach ($file in $files) {
        $relative = $file.FullName.Substring($SnapshotPath.Length).TrimStart('\')
        if ($relative.StartsWith("_meta\")) {
            continue
        }

        $destPath = Join-Path $DestinationPath $relative
        $destDir = Split-Path -Path $destPath -Parent
        if (-not (Test-Path -LiteralPath $destDir)) {
            New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        }
        Copy-Item -LiteralPath $file.FullName -Destination $destPath -Force
    }
}

$resolvedSource = (Resolve-Path -LiteralPath $SourceRepo).Path
$snapshotPath = Get-HotSnapshotPath -Root $HotSnapshotRoot -Name $SnapshotName
$primaryParent = Split-Path -Path $PrimaryPath -Parent

Write-Stamp "Source repo: $resolvedSource" White
Write-Stamp "Primary path: $PrimaryPath" White
Write-Stamp "Hot snapshot: $snapshotPath" White

if (-not (Test-Path -LiteralPath $primaryParent)) {
    New-Item -ItemType Directory -Path $primaryParent -Force | Out-Null
}

if (-not $RefreshOnly) {
    if (-not (Test-Path -LiteralPath $PrimaryPath)) {
        Write-Stamp "Cloning tracked base into $PrimaryPath" Cyan
        git clone --no-hardlinks $resolvedSource $PrimaryPath | Out-Null
    } else {
        Write-Stamp "Primary path already exists. Skipping clone and applying overlay only." Yellow
    }
}

if (-not (Test-Path -LiteralPath $PrimaryPath)) {
    throw "Primary path does not exist after clone step: $PrimaryPath"
}

Write-Stamp "Applying hot snapshot overlay" Cyan
Copy-SnapshotOverlay -SnapshotPath $snapshotPath -DestinationPath $PrimaryPath

Write-Stamp "Primary workspace ready at $PrimaryPath" Green
