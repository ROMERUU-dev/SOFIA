from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "docs" / "benchmark"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run all SOFIA benchmark cases and refresh comparisons.")
    parser.add_argument("--case-id", action="append", help="Run only this case id. Can be passed more than once.")
    parser.add_argument("--skip-run", action="store_true", help="Only refresh comparison files.")
    return parser


def case_dirs(selected: list[str] | None) -> list[Path]:
    if selected:
        return [(BENCHMARK_DIR / case_id).resolve() for case_id in selected]
    return sorted(path for path in BENCHMARK_DIR.iterdir() if path.is_dir() and (path / "input.json").exists())


def case_args(case_dir: Path) -> list[str]:
    payload = json.loads((case_dir / "input.json").read_text(encoding="utf-8"))
    args = [
        sys.executable,
        "scripts/benchmark_case.py",
        "--case-id",
        case_dir.name,
        "--kind",
        payload["kind"],
        "--approx",
        payload["approx"],
        "--ap",
        str(payload["ap"]),
        "--as",
        str(payload["as"]),
        "--topology",
        payload["topology"],
        "--opamp",
        payload.get("opamp", "TL082"),
        "--cap",
        str(payload.get("cap", "1e-8")),
        "--resistor-series",
        payload.get("resistor_series", "E24"),
        "--max-network-size",
        str(payload.get("max_network_size", "2")),
    ]
    if not payload.get("allow_resistor_arrays", True):
        args.append("--no-resistor-arrays")
    if not payload.get("auto_stage_capacitor", True):
        args.append("--no-auto-stage-capacitor")
    for name in ("fp", "fs", "fp1", "fp2", "fs1", "fs2"):
        value = payload.get(name)
        if value is not None:
            args.extend([f"--{name}", str(value)])
    return args


def write_report(results: list[dict[str, str]]) -> None:
    lines = [
        "# Benchmark Report",
        "",
        "Generated from the benchmark case folders. Cases marked `pending_legacy` still need `legacy.cir` from the original SOFIA on Windows.",
        "",
        "| Case | Status |",
        "| --- | --- |",
    ]
    for result in results:
        lines.append(f"| `{result['case_id']}` | `{result['status']}` |")
    lines.append("")
    (BENCHMARK_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    results: list[dict[str, str]] = []

    for case_dir in case_dirs(args.case_id):
        if not case_dir.exists():
            raise SystemExit(f"Missing benchmark case: {case_dir}")
        if not args.skip_run:
            subprocess.run(case_args(case_dir), cwd=ROOT, check=True)
        completed = subprocess.run(
            [sys.executable, "scripts/compare_case.py", str(case_dir), "--write-markdown"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        results.append(json.loads(completed.stdout))

    write_report(results)
    print(json.dumps({"cases": len(results), "report": str(BENCHMARK_DIR / "report.md")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
