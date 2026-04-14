[CmdletBinding()]
param(
    [string]$Source = $PSScriptRoot,
    [string[]]$Destinations = @(
        "D:\workspace-backups\champion_councl-hot",
        "G:\workspace-backups\champion_councl-hot"
    )
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
        return [pscustomobject]@{ Ready = $false; Reason = "No drive root found." }
    }
    if (-not (Test-Path -LiteralPath $root)) {
        return [pscustomobject]@{ Ready = $false; Reason = "Drive $root is not mounted." }
    }
    return [pscustomobject]@{ Ready = $true; Reason = "" }
}

function Copy-RelativeFile {
    param(
        [string]$RepoRoot,
        [string]$RelativePath,
        [string]$SnapshotRoot
    )

    $sourcePath = Join-Path $RepoRoot $RelativePath
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        throw "Missing source path: $sourcePath"
    }
    $destPath = Join-Path $SnapshotRoot $RelativePath
    $destDir = Split-Path -Path $destPath -Parent
    if (-not (Test-Path -LiteralPath $destDir)) {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    }
    Copy-Item -LiteralPath $sourcePath -Destination $destPath -Force
}

$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
Set-Location $resolvedSource

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$head = (git rev-parse HEAD).Trim()
$statusLines = @(git status --short)
$modified = @(git diff --name-only)
$untracked = @(git ls-files --others --exclude-standard)
$paths = @($modified + $untracked | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | Sort-Object -Unique)

if ($paths.Count -eq 0) {
    Write-Stamp "No modified or untracked files found. Nothing to snapshot." Yellow
    exit 0
}

Write-Stamp "Source: $resolvedSource" White
Write-Stamp ("Changed paths: " + $paths.Count) White

foreach ($destination in $Destinations) {
    $destState = Test-BackupDestination -Destination $destination
    if (-not $destState.Ready) {
        Write-Stamp "Skipping $destination - $($destState.Reason)" Yellow
        continue
    }

    $snapshotRoot = Join-Path $destination $timestamp
    $metaRoot = Join-Path $snapshotRoot "_meta"
    New-Item -ItemType Directory -Path $metaRoot -Force | Out-Null

    Write-Stamp "Writing hot snapshot to $snapshotRoot" Cyan

    $statusLines | Set-Content -LiteralPath (Join-Path $metaRoot "git_status_short.txt") -Encoding UTF8
    $modified | Set-Content -LiteralPath (Join-Path $metaRoot "modified_files.txt") -Encoding UTF8
    $untracked | Set-Content -LiteralPath (Join-Path $metaRoot "untracked_files.txt") -Encoding UTF8
    @(
        "timestamp=$timestamp"
        "source=$resolvedSource"
        "head=$head"
        "path_count=$($paths.Count)"
    ) | Set-Content -LiteralPath (Join-Path $metaRoot "snapshot_info.txt") -Encoding UTF8

    git diff --binary | Set-Content -LiteralPath (Join-Path $metaRoot "working_tree.diff") -Encoding UTF8

    foreach ($relativePath in $paths) {
        Copy-RelativeFile -RepoRoot $resolvedSource -RelativePath $relativePath -SnapshotRoot $snapshotRoot
    }

    Write-Stamp "Hot snapshot OK for $destination" Green
}
