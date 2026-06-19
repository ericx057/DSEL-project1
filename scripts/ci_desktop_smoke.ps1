$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$out = Join-Path $root "cache\desktop-smoke.out.log"
$err = Join-Path $root "cache\desktop-smoke.err.log"

New-Item -ItemType Directory -Force -Path (Join-Path $root "cache") | Out-Null

$venvPython = Join-Path $root ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    $python = $venvPython
}
else {
    $python = "python"
}

$source = @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class DesktopSmokeWindowApi {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    [DllImport("user32.dll")]
    public static extern bool PostMessage(IntPtr hWnd, uint msg, IntPtr wParam, IntPtr lParam);

    public static IntPtr FindVisibleWindow(uint targetPid, string title) {
        IntPtr found = IntPtr.Zero;
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pid != targetPid || !IsWindowVisible(hWnd)) {
                return true;
            }

            var text = new StringBuilder(512);
            GetWindowText(hWnd, text, text.Capacity);
            if (text.ToString() == title) {
                found = hWnd;
                return false;
            }
            return true;
        }, IntPtr.Zero);
        return found;
    }
}
"@

if (-not ("DesktopSmokeWindowApi" -as [type])) {
    Add-Type -TypeDefinition $source
}

$proc = Start-Process -FilePath $python `
    -ArgumentList @("-m", "src.desktop", "--show", "--no-hotkey") `
    -WorkingDirectory $root `
    -RedirectStandardOutput $out `
    -RedirectStandardError $err `
    -PassThru

$window = [IntPtr]::Zero
try {
    $deadline = (Get-Date).AddSeconds(25)
    $found = $false
    while ((Get-Date) -lt $deadline) {
        if ($proc.HasExited) {
            throw "Desktop app exited before creating the DSEL Code Search window."
        }

        $window = [DesktopSmokeWindowApi]::FindVisibleWindow([uint32]$proc.Id, "DSEL Code Search")
        if ($window -ne [IntPtr]::Zero) {
            $found = $true
            break
        }
        Start-Sleep -Milliseconds 300
    }

    if (-not $found) {
        throw "Timed out waiting for DSEL Code Search window."
    }

    Write-Host "Desktop smoke found DSEL Code Search window for process $($proc.Id)."
}
finally {
    if ($window -ne [IntPtr]::Zero) {
        [void][DesktopSmokeWindowApi]::PostMessage($window, 0x0010, [IntPtr]::Zero, [IntPtr]::Zero)
    }
    if (-not $proc.HasExited) {
        if (-not $proc.WaitForExit(3000)) {
            $proc.Kill()
        }
    }
}
