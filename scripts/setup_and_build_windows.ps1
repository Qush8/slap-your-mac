# Requires Windows with Python 3.10+ in PATH (recommended 3.10–3.13).
# Run from anywhere:
#   powershell -ExecutionPolicy Bypass -File .\scripts\setup_and_build_windows.ps1

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $ScriptDir
Set-Location $Root

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
$venvPip = Join-Path $Root ".venv\Scripts\pip.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating .venv..."
    py -3 -m venv .venv 2>$null
    if (-not (Test-Path $venvPython)) {
        python -m venv .venv
    }
}

if (-not (Test-Path $venvPython)) {
    Write-Error "Could not create .venv. Install Python 3 from python.org and retry."
    exit 1
}

& $venvPython -m pip install -q --upgrade pip
& $venvPip install -q -r requirements.txt -r requirements-build.txt

Write-Host "Building Windows folder with PyInstaller..."
& $venvPython -m PyInstaller slap-your-mac-win.spec

$distFolder = Join-Path $Root "dist\SlapYourMac"
$releases = Join-Path $Root "releases"
New-Item -ItemType Directory -Force -Path $releases | Out-Null
$zipOut = Join-Path $releases "SlapYourMac-windows.zip"
if (Test-Path $zipOut) {
    Remove-Item -Force $zipOut
}
Compress-Archive -Path $distFolder -DestinationPath $zipOut -Force

Write-Host ""
Write-Host "Done: $distFolder\SlapYourMac.exe"
Write-Host "Friend-ready zip: $zipOut"
Write-Host "(Share the zip; inside it is the whole SlapYourMac folder, not only the .exe.)"
