#!/usr/bin/env bash
# Builds dist/SOFIA-Filter-Studio-<version>-macos-<arch>.dmg with PyInstaller, on a Mac of that
# architecture (arm64 for Apple Silicon, x86_64 for Intel).
#   bash packaging/macos/build_dmg.sh
# Needs python3 (3.11+). PYTHON=/path/to/python picks the interpreter.
#
# The app is signed ad hoc, not with an Apple Developer ID, so macOS asks once before opening it:
# System Settings > Privacy & Security > Open Anyway (or right click > Open on older versions).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
app_name="SOFIA Filter Studio"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/src/sofia_filter_studio/__init__.py")"
arch="$(uname -m)"
build="$root/build/macos"
venv="$build/venv"

if [ ! -x "$venv/bin/python" ]; then
    "${PYTHON:-python3}" -m venv "$venv"
fi
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check pyinstaller "PySide6-Essentials>=6.7"
rm -rf "$build/sofia.iconset"
QT_QPA_PLATFORM=offscreen "$venv/bin/python" "$root/packaging/icons/render_icons.py" "$build/sofia.iconset" --iconset
iconutil -c icns "$build/sofia.iconset" -o "$build/sofia.icns"

"$venv/bin/python" -m PyInstaller --noconfirm --clean --onedir --windowed \
    --name "$app_name" \
    --icon "$build/sofia.icns" \
    --osx-bundle-identifier io.github.romeruu-dev.sofia-filter-studio \
    --paths "$root/src" \
    --add-data "$root/resources/models:resources/models" \
    --distpath "$build/dist" \
    --workpath "$build/pyinstaller" \
    --specpath "$build" \
    "$root/packaging/sofia_entry.py"

app="$build/dist/$app_name.app"
plist="$app/Contents/Info.plist"
plutil -replace CFBundleShortVersionString -string "$version" "$plist"
plutil -replace CFBundleVersion -string "$version" "$plist"
plutil -replace NSHighResolutionCapable -bool true "$plist"
plutil -replace LSApplicationCategoryType -string public.app-category.education "$plist"
plutil -replace NSHumanReadableCopyright -string "ROMERUU-dev" "$plist"
# Editing Info.plist breaks PyInstaller's ad hoc signature; sign the bundle again.
codesign --force --deep --sign - "$app"
codesign --verify --deep --strict "$app"

# The bundle has to start on its own before it is packaged.
SOFIA_SMOKE_TEST=1 QT_QPA_PLATFORM=offscreen "$app/Contents/MacOS/$app_name"

stage="$build/dmg"
rm -rf "$stage"
mkdir -p "$stage" "$root/dist"
cp -R "$app" "$stage/"
ln -s /Applications "$stage/Applications"
dmg="$root/dist/SOFIA-Filter-Studio-$version-macos-$arch.dmg"
rm -f "$dmg"
# hdiutil now and then fails with "Resource busy" right after the copy; try again.
for attempt in 1 2 3; do
    if hdiutil create -volname "$app_name" -srcfolder "$stage" -fs HFS+ -format UDZO -ov "$dmg"; then
        break
    fi
    [ "$attempt" = 3 ] && exit 1
    sleep 5
done
hdiutil verify "$dmg"
echo "Listo: $dmg"
