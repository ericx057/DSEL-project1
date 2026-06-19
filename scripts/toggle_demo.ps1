$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = Join-Path $root ".venv\Scripts\pythonw.exe"
$demo = Join-Path $root "demo.py"
$out = Join-Path $root "cache\demo-hotkey.out.log"
$err = Join-Path $root "cache\demo-hotkey.err.log"

New-Item -ItemType Directory -Force -Path (Join-Path $root "cache") | Out-Null

$source = @"
using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using System.Text;

public static class DemoWindowApi {
    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

    [DllImport("user32.dll")]
    public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

    public static List<IntPtr> FindWindowsForPids(HashSet<uint> pids) {
        var handles = new List<IntPtr>();
        EnumWindows(delegate(IntPtr hWnd, IntPtr lParam) {
            uint pid;
            GetWindowThreadProcessId(hWnd, out pid);
            if (pids.Contains(pid)) {
                handles.Add(hWnd);
            }
            return true;
        }, IntPtr.Zero);
        return handles;
    }
}
"@

if (-not ("DemoWindowApi" -as [type])) {
    Add-Type -TypeDefinition $source
}

$procs = Get-CimInstance Win32_Process -Filter "name = 'python.exe' OR name = 'pythonw.exe'" |
    Where-Object { $_.CommandLine -like "*demo.py*" }

if (-not $procs) {
    Start-Process -FilePath $python -ArgumentList @("-u", $demo, "--show") `
        -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
    Start-Sleep -Milliseconds 800
    exit 0
}

$pidSet = New-Object "System.Collections.Generic.HashSet[uint32]"
foreach ($proc in $procs) {
    [void]$pidSet.Add([uint32]$proc.ProcessId)
}

$windows = [DemoWindowApi]::FindWindowsForPids($pidSet)
if ($windows.Count -eq 0) {
    Start-Process -FilePath $python -ArgumentList @("-u", $demo, "--show") `
        -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
    Start-Sleep -Milliseconds 800
    exit 0
}

$anyVisible = $false
foreach ($hwnd in $windows) {
    if ([DemoWindowApi]::IsWindowVisible($hwnd)) {
        $anyVisible = $true
        break
    }
}

if ($anyVisible) {
    foreach ($hwnd in $windows) {
        [void][DemoWindowApi]::ShowWindow($hwnd, 0)
    }
}
else {
    foreach ($hwnd in $windows) {
        [void][DemoWindowApi]::ShowWindow($hwnd, 9)
        [void][DemoWindowApi]::SetForegroundWindow($hwnd)
    }
}
