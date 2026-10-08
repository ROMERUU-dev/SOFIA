# Builds dist\SOFIA-Filter-Studio.exe (single file, GUI) with PyInstaller.
# Requires Python 3.11+ (python.org installer). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$venv = Join-Path $root "build\venv"

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $Python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --quiet --disable-pip-version-check pyinstaller "PySide6-Essentials>=6.7"
if ($LASTEXITCODE -ne 0) { throw "Could not install the build requirements." }

# Absolute paths: PyInstaller resolves relative ones against --specpath.
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name "SOFIA-Filter-Studio" `
    --paths (Join-Path $root "src") `
    --add-data "$(Join-Path $root 'resources\models');resources\models" `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build\pyinstaller") `
    --specpath (Join-Path $root "build") `
    (Join-Path $root "packaging\windows\sofia_entry.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }
Write-Host "Listo: $(Join-Path $root 'dist\SOFIA-Filter-Studio.exe')"
