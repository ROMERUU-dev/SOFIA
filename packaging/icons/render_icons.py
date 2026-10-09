"""Render packaging/icons/sofia.svg to PNG files (needs PySide6).

    python packaging/icons/render_icons.py OUT_DIR [--iconset]

Writes OUT_DIR/<size>.png for the Linux icon theme, or with --iconset the names macOS iconutil wants
(icon_16x16.png, icon_16x16@2x.png, ...).
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

SOURCE = Path(__file__).with_name("sofia.svg")
SIZES = (16, 32, 48, 64, 128, 256, 512)


def render(size: int, path: Path) -> None:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(str(SOURCE)).render(painter)
    painter.end()
    if not image.save(str(path), "PNG"):
        raise SystemExit(f"No se pudo escribir {path}")


def main() -> None:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    app = QGuiApplication.instance() or QGuiApplication(["render_icons", "-platform", "offscreen"])
    if "--iconset" in sys.argv:
        for size in (16, 32, 128, 256, 512):
            render(size, out / f"icon_{size}x{size}.png")
            render(size * 2, out / f"icon_{size}x{size}@2x.png")
    else:
        for size in SIZES:
            render(size, out / f"{size}.png")
    del app


if __name__ == "__main__":
    main()
