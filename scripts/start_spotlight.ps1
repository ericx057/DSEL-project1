$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$venvPythonw = Join-Path $root ".venv\Scripts\pythonw.exe"
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$out = Join-Path $root "cache\spotlight.out.log"
$err = Join-Path $root "cache\spotlight.err.log"

New-Item -ItemType Directory -Force -Path (Join-Path $root "cache") | Out-Null

if (Test-Path $venvPythonw) {
    $python = $venvPythonw
}
elseif (Test-Path $venvPython) {
    $python = $venvPython
}
else {
    $python = "python"
}

$existing = @()
try {
    $existing = Get-CimInstance Win32_Process -Filter "name = 'python.exe' OR name = 'pythonw.exe'" |
        Where-Object { $_.CommandLine -like "*-m src.desktop*" }
}
catch {
    $existing = @()
}

if ($existing) {
    exit 0
}

Start-Process -FilePath $python -ArgumentList @("-m", "src.desktop") `
    -WorkingDirectory $root -RedirectStandardOutput $out -RedirectStandardError $err -WindowStyle Hidden
