"""Assemble the web version (static site for GitHub Pages).

The page runs the same Python package in the browser with Pyodide: this script copies ``web/`` and
packs ``src/sofia_filter_studio`` (without the Qt interface) plus the opamp models into a zip.

    python scripts/build_web.py            # writes _site/
    python -m http.server -d _site 8000    # then open http://localhost:8000
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sofia_filter_studio.forms import options  # noqa: E402

WEB_FILES = ("index.html", "style.css", "app.js", "plot.js", "worker.js")


def bundle_files() -> list[Path]:
    package = ROOT / "src" / "sofia_filter_studio"
    sources = [path for path in package.rglob("*.py") if "gui" not in path.relative_to(package).parts]
    models = [path for path in (ROOT / "resources" / "models").iterdir() if path.is_file()]
    return sorted(sources + models)


def bundle_bytes() -> bytes:
    """Zip with fixed timestamps, so the same sources always give the same file name."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path in bundle_files():
            info = zipfile.ZipInfo(path.relative_to(ROOT).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    return buffer.getvalue()


def build(out_dir: Path) -> Path:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)
    for name in WEB_FILES:
        shutil.copy2(ROOT / "web" / name, out_dir / name)
    data = bundle_bytes()
    # Content hash in the name: browsers and the Pages cache never serve an old package.
    bundle = f"sofia-{hashlib.sha256(data).hexdigest()[:10]}.zip"
    (out_dir / bundle).write_bytes(data)
    page_options = options() | {"bundle": bundle}
    (out_dir / "options.json").write_text(json.dumps(page_options, ensure_ascii=False, indent=1), encoding="utf-8")
    return out_dir


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=ROOT / "_site", help="output folder (default: _site)")
    args = parser.parse_args()
    out_dir = build(args.out.absolute())
    files = sorted(path.name for path in out_dir.iterdir())
    print(f"Sitio listo en {out_dir}: {', '.join(files)}")


if __name__ == "__main__":
    main()
