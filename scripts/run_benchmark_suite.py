from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from simulate_case import find_simulator


ROOT = Path(__file__).absolute().parents[1]
BENCHMARK_DIR = ROOT / "docs" / "benchmark"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run all SOFIA benchmark cases and refresh comparisons.")
    parser.add_argument("--case-id", action="append", help="Run only this case id. Can be passed more than once.")
    parser.add_argument("--skip-run", action="store_true", help="Only refresh comparison files.")
    parser.add_argument("--skip-sim", action="store_true", help="Do not simulate the netlists against the spec.")
    parser.add_argument("--spice", help="Path to LTspice or ngspice (default: $SOFIA_SPICE or auto-detection).")
    return parser


def case_dirs(selected: list[str] | None) -> list[Path]:
    if selected:
        return [(BENCHMARK_DIR / case_id).absolute() for case_id in selected]
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
        payload.get("resistor_series", "E96"),
        "--max-network-size",
        str(payload.get("max_network_size", "2")),
    ]
    if payload.get("allow_resistor_arrays", False):
        args.append("--resistor-arrays")
    if not payload.get("auto_stage_capacitor", True):
        args.append("--no-auto-stage-capacitor")
    for name in ("fp", "fs", "fp1", "fp2", "fs1", "fs2"):
        value = payload.get(name)
        if value is not None:
            args.extend([f"--{name}", str(value)])
    return args


def write_report(results: list[dict[str, str]], simulated: bool) -> None:
    lines = [
        "# Benchmark Report",
        "",
        "Generated from the benchmark case folders. Cases marked `pending_legacy` still need `legacy.cir` from the original SOFIA on Windows.",
        "",
    ]
    if simulated:
        lines.extend(
            [
                "Spec columns come from `scripts/simulate_case.py`: each netlist is simulated (AC) and checked against",
                "`input.json` (passband ripple <= Ap, stopband attenuation >= As). `limitacion_del_opamp` means the same",
                "circuit meets the spec with ideal op amps, so the deviation comes from the op amp model, not the design.",
                "",
                "| Case | Structure vs legacy | New version | Legacy |",
                "| --- | --- | --- | --- |",
            ]
        )
        for result in results:
            lines.append(
                f"| `{result['case_id']}` | `{result['status']}` | {_spec_cell(result, 'modern')} | {_spec_cell(result, 'legacy')} |"
            )
    else:
        lines.extend(["| Case | Status |", "| --- | --- |"])
        for result in results:
            lines.append(f"| `{result['case_id']}` | `{result['status']}` |")
    lines.append("")
    (BENCHMARK_DIR / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _spec_cell(result: dict[str, str], label: str) -> str:
    verdict = result.get(f"{label}_spec", "sin_simular")
    diagnosis = result.get(f"{label}_diagnosis")
    return f"`{verdict}` ({diagnosis})" if diagnosis and diagnosis != "funciona" else f"`{verdict}`"


def main() -> int:
    args = build_parser().parse_args()
    simulator = None if args.skip_sim else find_simulator(args.spice)
    if not args.skip_sim and simulator is None:
        print("No SPICE simulator found; skipping spec simulation (use --spice or SOFIA_SPICE).", file=sys.stderr)
    results: list[dict[str, str]] = []

    for case_dir in case_dirs(args.case_id):
        if not case_dir.exists():
            raise SystemExit(f"Missing benchmark case: {case_dir}")
        if not args.skip_run:
            subprocess.run(case_args(case_dir), cwd=ROOT, check=True)
        diagnoses: dict[str, str] = {}
        if simulator is not None:
            simulated = subprocess.run(
                [sys.executable, "scripts/simulate_case.py", str(case_dir), "--spice", str(simulator)],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            sim_summary = json.loads(simulated.stdout)
            diagnoses = {key: value for key, value in sim_summary.items() if key.endswith("_diagnosis")}
        completed = subprocess.run(
            [sys.executable, "scripts/compare_case.py", str(case_dir), "--write-markdown"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        results.append({**json.loads(completed.stdout), **diagnoses})

    write_report(results, simulated=simulator is not None)
    print(json.dumps({"cases": len(results), "report": str(BENCHMARK_DIR / "report.md")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
