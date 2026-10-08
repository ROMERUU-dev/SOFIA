"""Print docs/manual/manual.html to docs/manual/SOFIA-manual.pdf with headless Edge or Chrome.

The screenshots it uses live in web/img/ (shared with the presentation page).

    python scripts/build_manual.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
SOURCE = ROOT / "docs" / "manual" / "manual.html"
OUTPUT = ROOT / "docs" / "manual" / "SOFIA-manual.pdf"
CANDIDATES = [
    os.environ.get("SOFIA_BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
]
COMMANDS = ["google-chrome", "chromium", "chromium-browser", "microsoft-edge", "msedge"]


def find_browser() -> str:
    for path in CANDIDATES:
        if path and Path(path).exists():
            return path
    for name in COMMANDS:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit("No se encontro Edge ni Chrome; indica la ruta con la variable SOFIA_BROWSER.")


def main() -> None:
    browser = find_browser()
    OUTPUT.unlink(missing_ok=True)
    # The browser's helper processes can hold the profile folder for a moment after it exits.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile}",
                "--no-pdf-header-footer",
                "--virtual-time-budget=5000",
                f"--print-to-pdf={OUTPUT}",
                SOURCE.as_uri(),
            ],
            check=True,
            capture_output=True,
            timeout=120,
        )
    if not OUTPUT.exists() or OUTPUT.stat().st_size < 10_000:
        raise SystemExit("El navegador no genero el PDF")
    print(f"Manual listo: {OUTPUT.relative_to(ROOT)} ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
