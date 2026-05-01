param(
    [string]$Url = "https://tostido-champion-council.hf.space",
    [string]$View = "render",
    [string]$Source = "external",
    [double]$Interval = 0.05,
    [double]$Timeout = 8.0,
    [switch]$Diagnostics
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcher = Join-Path $root "run_text_theater.ps1"

if (-not (Test-Path -LiteralPath $launcher)) {
    throw "Missing launcher: $launcher"
}

$psExe = (Get-Process -Id $PID).Path
if (-not $psExe) {
    $pwsh = Get-Command "pwsh.exe" -ErrorAction SilentlyContinue
    $psExe = if ($pwsh) { $pwsh.Source } else { "powershell.exe" }
}

$argList = @(
    "-NoLogo",
    "-ExecutionPolicy", "Bypass",
    "-File", ('"' + $launcher + '"'),
    "--url", ('"' + $Url.TrimEnd('/') + '"'),
    "--source", ('"' + $Source + '"'),
    "--view", ('"' + $View + '"'),
    "--interval", ([string]$Interval),
    "--timeout", ([string]$Timeout)
)

if ($Diagnostics) {
    $argList += "--diagnostics"
}

$proc = Start-Process -FilePath $psExe -ArgumentList $argList -WorkingDirectory $root -PassThru
Write-Host "Opened Space Text Theater from $Url (PID $($proc.Id))."
