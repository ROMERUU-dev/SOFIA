# Builds dist\SOFIA-Filter-Studio-<version>-windows.exe (single file, GUI) with PyInstaller.
# Requires Python 3.11+ (python.org installer). Run from the repo root:
#   powershell -ExecutionPolicy Bypass -File packaging\windows\build_exe.ps1
param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$venv = Join-Path $root "build\venv"
$init = Join-Path $root "src\sofia_filter_studio\__init__.py"
$version = (Select-String -Path $init -Pattern '^__version__ = "(.+)"').Matches[0].Groups[1].Value
$name = "SOFIA-Filter-Studio-$version-windows"

if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    & $Python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install --quiet --disable-pip-version-check pyinstaller pillow "PySide6-Essentials>=6.7"
if ($LASTEXITCODE -ne 0) { throw "Could not install the build requirements." }

# Icon: the PNGs rendered from packaging\icons\sofia.svg, packed into an .ico.
$icons = Join-Path $root "build\icons"
$env:QT_QPA_PLATFORM = "offscreen"
& $py (Join-Path $root "packaging\icons\render_icons.py") $icons
if ($LASTEXITCODE -ne 0) { throw "Could not render the icon." }
$ico = Join-Path $icons "sofia.ico"
& $py -c "import sys; from PIL import Image; Image.open(sys.argv[1]).save(sys.argv[2], sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])" (Join-Path $icons "256.png") $ico
if ($LASTEXITCODE -ne 0) { throw "Could not write the .ico file." }

# Absolute paths: PyInstaller resolves relative ones against --specpath.
& $py -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name $name `
    --icon $ico `
    --paths (Join-Path $root "src") `
    --add-data "$(Join-Path $root 'resources\models');resources\models" `
    --distpath (Join-Path $root "dist") `
    --workpath (Join-Path $root "build\pyinstaller") `
    --specpath (Join-Path $root "build") `
    (Join-Path $root "packaging\sofia_entry.py")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

# The .exe has to start on its own (window, schematic, routed board) before it counts as built.
$exe = Join-Path $root "dist\$name.exe"
$env:SOFIA_SMOKE_TEST = "1"
$process = Start-Process -FilePath $exe -Wait -PassThru
Remove-Item Env:SOFIA_SMOKE_TEST
Remove-Item Env:QT_QPA_PLATFORM
if ($process.ExitCode -ne 0) { throw "The smoke test of the .exe failed (exit code $($process.ExitCode))." }
Write-Host "Listo: $exe"
