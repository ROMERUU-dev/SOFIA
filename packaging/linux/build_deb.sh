#!/usr/bin/env bash
# Builds dist/sofia-filter-studio_<version>_<arch>.deb with PyInstaller. Run it on the oldest Ubuntu
# the package should support (22.04): it then installs there and on later Ubuntu and Debian releases.
#   bash packaging/linux/build_deb.sh
# Needs python3 (3.11+) with venv, dpkg-deb and objdump. PYTHON=/path/to/python picks the interpreter.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
name="sofia-filter-studio"
version="$(sed -n 's/^__version__ = "\(.*\)"$/\1/p' "$root/src/sofia_filter_studio/__init__.py")"
arch="$(dpkg --print-architecture)"
build="$root/build/linux"
venv="$build/venv"

if [ ! -x "$venv/bin/python" ]; then
    "${PYTHON:-python3}" -m venv "$venv"
fi
"$venv/bin/python" -m pip install --quiet --disable-pip-version-check pyinstaller "PySide6-Essentials>=6.7"
QT_QPA_PLATFORM=offscreen "$venv/bin/python" "$root/packaging/icons/render_icons.py" "$build/icons"

"$venv/bin/python" -m PyInstaller --noconfirm --clean --onedir \
    --name "$name" \
    --paths "$root/src" \
    --add-data "$root/resources/models:resources/models" \
    --distpath "$build/dist" \
    --workpath "$build/pyinstaller" \
    --specpath "$build" \
    "$root/packaging/sofia_entry.py"

# PyInstaller also copies the libraries of the desktop that Qt and its GTK theme link to (X11 and
# xkbcommon, fonts, glib, GTK, the C++ runtime). Next to the newer ones of a later release they crash
# (libxkbcommon on Ubuntu 26.04), so they come from the system instead (see Depends). The GTK theme and
# the platform plugins other than X11, Wayland and offscreen go as well.
internal="$build/dist/$name/_internal"
for pattern in 'libstdc++.so*' 'libgcc_s.so*' 'libz.so*' 'libffi.so*' 'liblzma.so*' 'liblz4.so*' 'libzstd.so*' \
    'libbsd.so*' 'libmd.so*' 'libuuid.so*' 'libcap.so*' 'libgcrypt.so*' 'libgpg-error.so*' 'libsystemd.so*' 'libdbus-1.so*' \
    'libselinux.so*' 'libmount.so*' 'libblkid.so*' 'libpcre.so*' 'libpcre2-*.so*' 'libglib-2.0.so*' 'libgobject-2.0.so*' \
    'libgio-2.0.so*' 'libgmodule-2.0.so*' 'libgthread-2.0.so*' 'libexpat.so*' 'libpng16.so*' 'libbrotli*.so*' \
    'libfreetype.so*' 'libfontconfig.so*' 'libharfbuzz.so*' 'libgraphite2.so*' 'libxkbcommon*.so*' 'libxcb*.so*' \
    'libX*.so*' 'libgtk-3.so*' 'libgdk-3.so*' 'libgdk_pixbuf-2.0.so*' 'libatk*.so*' 'libatspi.so*' 'libcairo*.so*' \
    'libpango*.so*' 'libpixman-1.so*' 'libepoxy.so*' 'libfribidi.so*' 'libthai.so*' 'libdatrie.so*' 'libjpeg.so*' \
    'libQt6EglFS*.so*'; do
    find "$internal" -maxdepth 1 -name "$pattern" -delete
done
plugins="$internal/PySide6/Qt/plugins"
rm -rf "$plugins/egldeviceintegrations" "$plugins/platformthemes/libqgtk3.so"
for plugin in qeglfs qlinuxfb qminimal qminimalegl qvkkhrdisplay qvnc; do
    rm -f "$plugins/platforms/lib$plugin.so"
done

# The bundle has to start on its own before it is packaged.
SOFIA_SMOKE_TEST=1 QT_QPA_PLATFORM=offscreen "$build/dist/$name/$name"

pkg="$build/pkg"
rm -rf "$pkg"
mkdir -p "$pkg/DEBIAN" "$pkg/opt" "$pkg/usr/bin" "$pkg/usr/share/doc/$name"
cp -a "$build/dist/$name" "$pkg/opt/$name"
ln -s "/opt/$name/$name" "$pkg/usr/bin/$name"
install -D -m 644 "$root/packaging/linux/$name.desktop" "$pkg/usr/share/applications/$name.desktop"
for size in 16 32 48 64 128 256 512; do
    install -D -m 644 "$build/icons/$size.png" "$pkg/usr/share/icons/hicolor/${size}x${size}/apps/$name.png"
done
install -D -m 644 "$root/packaging/icons/sofia.svg" "$pkg/usr/share/icons/hicolor/scalable/apps/$name.svg"
cat > "$pkg/usr/share/doc/$name/copyright" <<EOF
Format: https://www.debian.org/doc/packaging-manuals/copyright-format/1.0/
Upstream-Name: SOFIA Filter Studio
Upstream-Contact: ROMERUU-dev <juvenal.romero@uabc.edu.mx>
Source: https://github.com/ROMERUU-dev/SOFIA

Files: *
Copyright: ROMERUU-dev
License: Proprietary

Files: opt/$name/_internal/PySide6/* opt/$name/_internal/shiboken6/*
Copyright: The Qt Company Ltd.
License: LGPL-3.0-only
 Qt 6 and PySide6, used as shared libraries. The text of the license is in
 /usr/share/common-licenses/LGPL-3.

Files: opt/$name/_internal/libpython*
Copyright: Python Software Foundation
License: PSF-2.0
EOF
find "$pkg" -type d -exec chmod 755 {} +

# Oldest glibc the bundled binaries ask for.
glibc="$(find "$pkg/opt" -type f \( -name '*.so*' -o -perm -u+x \) -exec objdump -T {} + 2>/dev/null \
    | grep -o 'GLIBC_[0-9][0-9.]*' | sed 's/GLIBC_//' | sort -uV | tail -n 1)"
# Libraries Qt and Python load from the system (C++ runtime, glib, fonts, OpenGL, X11 and Wayland);
# Ubuntu 24.04 renamed glib and libpng (t64).
depends="libc6 (>= $glibc), libstdc++6, libgcc-s1, zlib1g, libffi8, libglib2.0-0t64 | libglib2.0-0, libdbus-1-3,
 libfontconfig1, libfreetype6, libpng16-16t64 | libpng16-16, libgl1, libegl1, libxkbcommon0, libxkbcommon-x11-0,
 libx11-6, libx11-xcb1, libxcb1, libxcb-cursor0, libxcb-glx0, libxcb-icccm4, libxcb-image0, libxcb-keysyms1,
 libxcb-randr0, libxcb-render0, libxcb-render-util0, libxcb-shape0, libxcb-shm0, libxcb-sync1, libxcb-xfixes0,
 libxcb-xinerama0, libxcb-xkb1, libwayland-client0, libwayland-cursor0, libwayland-egl1"
cat > "$pkg/DEBIAN/control" <<EOF
Package: $name
Version: $version
Section: electronics
Priority: optional
Architecture: $arch
Maintainer: ROMERUU-dev <juvenal.romero@uabc.edu.mx>
Installed-Size: $(du -sk --exclude=DEBIAN "$pkg" | cut -f1)
Depends: $depends
Homepage: https://romeruu-dev.github.io/SOFIA/
Description: diseño de filtros activos analógicos
 SOFIA Filter Studio calcula el orden, las etapas y los componentes comerciales
 de filtros Butterworth y Chebyshev (pasa bajas, pasa altas, pasa banda y
 rechaza banda) con topologías Sallen-Key, MFB, Tow-Thomas y Antoniou.
 .
 Genera el netlist SPICE para LTspice o ngspice, el esquemático, la lista de
 materiales y la placa ruteada (Gerber y proyecto de KiCad), en SMD o
 through-hole.
EOF

mkdir -p "$root/dist"
deb="$root/dist/${name}_${version}_${arch}.deb"
dpkg-deb --root-owner-group -Zxz --build "$pkg" "$deb"
dpkg-deb --info "$deb"
echo "Listo: $deb"
