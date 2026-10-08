from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).absolute().parents[1]
BENCHMARK_DIR = ROOT / "docs" / "benchmark"
TEMPLATE = BENCHMARK_DIR / "case_template.md"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create a benchmark case for SOFIA Filter Studio.")
    parser.add_argument("--case-id", required=True, help="Example: case_01_lowpass_butterworth")
    parser.add_argument("--kind", required=True)
    parser.add_argument("--approx", required=True)
    parser.add_argument("--ap", required=True)
    parser.add_argument("--as", dest="a_stop", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--opamp", default="TL082")
    parser.add_argument("--cap", default="1e-8")
    parser.add_argument("--resistor-series", default="E24")
    parser.add_argument("--max-network-size", default="2")
    parser.add_argument("--no-resistor-arrays", action="store_true")
    parser.add_argument("--no-auto-stage-capacitor", action="store_true")
    parser.add_argument("--fp")
    parser.add_argument("--fs")
    parser.add_argument("--fp1")
    parser.add_argument("--fp2")
    parser.add_argument("--fs1")
    parser.add_argument("--fs2")
    parser.add_argument("--legacy-netlist", help="Optional path to the old netlist to copy as legacy.cir")
    return parser


def make_case_dir(case_id: str) -> Path:
    case_dir = BENCHMARK_DIR / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    return case_dir


def build_cli_command(args: argparse.Namespace, case_dir: Path) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "sofia_filter_studio",
        "--kind",
        args.kind,
        "--approx",
        args.approx,
        "--ap",
        str(args.ap),
        "--as",
        str(args.a_stop),
        "--topology",
        args.topology,
        "--opamp",
        args.opamp,
        "--cap",
        str(args.cap),
        "--resistor-series",
        args.resistor_series,
        "--max-network-size",
        str(args.max_network_size),
        "--netlist-out",
        # Relative to ROOT (the CLI runs there) so command.txt/stdout.txt are portable.
        (case_dir / "generated.cir").relative_to(ROOT).as_posix(),
    ]
    if args.no_resistor_arrays:
        cmd.append("--no-resistor-arrays")
    if args.no_auto_stage_capacitor:
        cmd.append("--no-auto-stage-capacitor")
    for name in ("fp", "fs", "fp1", "fp2", "fs1", "fs2"):
        value = getattr(args, name)
        if value is not None:
            cmd.extend([f"--{name}", str(value)])
    return cmd


def write_case_markdown(case_dir: Path, args: argparse.Namespace) -> None:
    if (case_dir / "case.md").exists():
        return
    content = TEMPLATE.read_text(encoding="utf-8")
    content = content.replace("{{case_id}}", args.case_id)
    (case_dir / "case.md").write_text(content, encoding="utf-8")


def write_input_json(case_dir: Path, args: argparse.Namespace) -> None:
    payload = {
        "kind": args.kind,
        "approx": args.approx,
        "ap": args.ap,
        "as": args.a_stop,
        "topology": args.topology,
        "opamp": args.opamp,
        "cap": args.cap,
        "resistor_series": args.resistor_series,
        "max_network_size": args.max_network_size,
        "allow_resistor_arrays": not args.no_resistor_arrays,
        "auto_stage_capacitor": not args.no_auto_stage_capacitor,
        "fp": args.fp,
        "fs": args.fs,
        "fp1": args.fp1,
        "fp2": args.fp2,
        "fs1": args.fs1,
        "fs2": args.fs2,
    }
    (case_dir / "input.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_case(case_dir: Path, args: argparse.Namespace) -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    cmd = build_cli_command(args, case_dir)
    completed = subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload, _ = json.JSONDecoder().raw_decode(completed.stdout)
    (case_dir / "result.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (case_dir / "stdout.txt").write_text(completed.stdout, encoding="utf-8")
    (case_dir / "command.txt").write_text(shlex.join(["python", *cmd[1:]]) + "\n", encoding="utf-8")


def copy_legacy_netlist(case_dir: Path, legacy_path: str | None) -> None:
    if not legacy_path:
        return
    src = Path(legacy_path).expanduser().absolute()
    dst = case_dir / "legacy.cir"
    if src != dst.absolute():
        shutil.copyfile(src, dst)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    case_dir = make_case_dir(args.case_id)
    write_case_markdown(case_dir, args)
    write_input_json(case_dir, args)
    run_case(case_dir, args)
    copy_legacy_netlist(case_dir, args.legacy_netlist)
    (case_dir / "notes.txt").touch(exist_ok=True)
    print(f"Benchmark case created at {case_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
