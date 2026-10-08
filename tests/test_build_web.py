"""The web site build: layout of the output and no broken local links."""

import importlib.util
import json
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).absolute().parents[1]
_spec = importlib.util.spec_from_file_location("build_web", ROOT / "scripts" / "build_web.py")
build_web = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_web)


class _References(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.paths: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.paths.append(value)
            elif name == "srcset" and value:
                self.paths.extend(part.split()[0] for part in value.split(","))


def local_references(html_file: Path) -> list[str]:
    parser = _References()
    parser.feed(html_file.read_text(encoding="utf-8"))
    skip = ("http://", "https://", "#", "data:", "mailto:")
    return [path.split("#")[0] for path in parser.paths if not path.startswith(skip) and path.split("#")[0]]


class BuildWebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory()
        cls.site = build_web.build(Path(cls.tmp.name) / "site")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_layout(self) -> None:
        for name in ("index.html", "landing.css", "SOFIA-manual.pdf", "img/og.png", "app/index.html", "app/worker.js"):
            with self.subTest(name=name):
                self.assertTrue((self.site / name).is_file())
        options = json.loads((self.site / "app" / "options.json").read_text(encoding="utf-8"))
        self.assertTrue((self.site / "app" / options["bundle"]).is_file())
        self.assertEqual(options["defaults"]["series"], "E96")

    def test_local_links_resolve(self) -> None:
        for page in ("index.html", "app/index.html"):
            html_file = self.site / page
            for reference in local_references(html_file):
                with self.subTest(page=page, reference=reference):
                    self.assertTrue((html_file.parent / reference).resolve().exists())

    def test_manual_images_exist(self) -> None:
        manual = ROOT / "docs" / "manual" / "manual.html"
        for reference in local_references(manual):
            with self.subTest(reference=reference):
                self.assertTrue((manual.parent / reference).resolve().exists())


if __name__ == "__main__":
    unittest.main()
