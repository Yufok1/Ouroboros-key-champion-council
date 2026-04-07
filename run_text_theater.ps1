$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

if (-not $env:WEB_HOST) { $env:WEB_HOST = "127.0.0.1" }
if (-not $env:WEB_PORT) { $env:WEB_PORT = "7866" }

$stateDir = Join-Path $root "data"
$statePath = Join-Path $stateDir "text_theater_window.json"
if (-not (Test-Path $stateDir)) {
    New-Item -ItemType Directory -Path $stateDir | Out-Null
}
$state = [ordered]@{
    pid = $PID
    started_ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds()
    launcher = $MyInvocation.MyCommand.Path
    host = $(if ($env:WT_SESSION) { "windows-terminal-profile" } else { "powershell-process" })
    web_host = $env:WEB_HOST
    web_port = $env:WEB_PORT
}
$state | ConvertTo-Json -Depth 4 | Set-Content -Path $statePath -Encoding UTF8

try {
    $fontStepDown = 6
    if ($env:TEXT_THEATER_FONT_STEP_DOWN) {
        $fontStepDown = [Math]::Max(0, [int]$env:TEXT_THEATER_FONT_STEP_DOWN)
    }

    if ($fontStepDown -gt 0 -and -not $env:WT_SESSION) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct COORD {
    public short X;
    public short Y;
}
[StructLayout(LayoutKind.Sequential, CharSet=CharSet.Unicode)]
public struct CONSOLE_FONT_INFOEX {
    public uint cbSize;
    public uint nFont;
    public COORD dwFontSize;
    public int FontFamily;
    public int FontWeight;
    [MarshalAs(UnmanagedType.ByValTStr, SizeConst=32)]
    public string FaceName;
}
public static class ConsoleFontNative {
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern IntPtr GetStdHandle(int nStdHandle);

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool GetCurrentConsoleFontEx(IntPtr hConsoleOutput, bool bMaximumWindow, ref CONSOLE_FONT_INFOEX info);

    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool SetCurrentConsoleFontEx(IntPtr hConsoleOutput, bool bMaximumWindow, ref CONSOLE_FONT_INFOEX info);
}
"@ -ErrorAction SilentlyContinue | Out-Null

        $handle = [ConsoleFontNative]::GetStdHandle(-11)
        $fontInfo = New-Object CONSOLE_FONT_INFOEX
        $fontInfo.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($fontInfo)
        if ([ConsoleFontNative]::GetCurrentConsoleFontEx($handle, $false, [ref]$fontInfo)) {
            $currentHeight = [int]$fontInfo.dwFontSize.Y
            if ($currentHeight -gt 0) {
                $targetHeight = [Math]::Max(8, $currentHeight - $fontStepDown)
                if ($targetHeight -ne $currentHeight) {
                    if ([int]$fontInfo.dwFontSize.X -gt 0) {
                        $scaledWidth = [Math]::Round(([double]$fontInfo.dwFontSize.X * [double]$targetHeight) / [double]$currentHeight)
                        $fontInfo.dwFontSize.X = [int16]([Math]::Max(1, [int]$scaledWidth))
                    }
                    $fontInfo.dwFontSize.Y = [int16]$targetHeight
                    [ConsoleFontNative]::SetCurrentConsoleFontEx($handle, $false, [ref]$fontInfo) | Out-Null
                }
            }
        }
    }
} catch {
}

python scripts/text_theater.py @args
