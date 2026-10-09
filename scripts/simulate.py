"""Simulate a SOFIA netlist with SPICE (LTspice or ngspice) and check it against the specification.

    python scripts/simulate.py filtro.cir --kind lowpass --fp 1000 --fs 2000 --ap 1 --as 40
    python scripts/simulate.py banda.cir --kind bandpass --fp 800 1200 --fs 500 2000 --ap 1 --as 30

The netlist is simulated twice, with the real op amp model and with ideal op amps, which separates
design errors from op amp limitations. The tests in tests/test_simulation.py use the same functions.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).absolute().parents[1]
MODELS_DIR = ROOT / "resources" / "models"

LTSPICE_CANDIDATES = [
    r"C:\Program Files\ADI\LTspice\LTspice.exe",
    r"C:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
    r"D:\Program Files\LTC\LTspiceXVII\XVIIx64.exe",
    r"C:\Program Files (x86)\LTC\LTspiceIV\scad3.exe",
]

INCLUDE_RE = re.compile(r'^\s*\.(include|inc|lib)\s+"?([^"\r\n]+?)"?\s*$', re.IGNORECASE)
DROP_RE = re.compile(r"^\s*\.(ac|tran|dc|op|noise|probe|plot|print|end)\b", re.IGNORECASE)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Simulate a SOFIA netlist and check it against its spec.")
    parser.add_argument("netlist", help="Netlist (.cir) written by SOFIA.")
    parser.add_argument("--kind", required=True, choices=["lowpass", "highpass", "bandpass", "bandstop"])
    parser.add_argument("--fp", type=float, nargs="+", required=True, help="Passband edge(s) in Hz.")
    parser.add_argument("--fs", type=float, nargs="+", required=True, help="Stopband edge(s) in Hz.")
    parser.add_argument("--ap", type=float, required=True, help="Maximum passband ripple in dB.")
    parser.add_argument("--as", dest="a_stop", type=float, required=True, help="Minimum stopband attenuation in dB.")
    parser.add_argument("--spice", help="Path to LTspice or ngspice. Defaults to $SOFIA_SPICE or auto-detection.")
    parser.add_argument("--output-node", default="OUT", help="Node probed as filter output.")
    parser.add_argument("--ripple-tol", type=float, default=0.15, help="Extra passband ripple allowed, in dB.")
    parser.add_argument("--atten-tol", type=float, default=0.5, help="Stopband attenuation shortfall allowed, in dB.")
    return parser


def spec_from_args(args: argparse.Namespace) -> dict[str, Any]:
    spec: dict[str, Any] = {"kind": args.kind, "ap": args.ap, "as": args.a_stop}
    edges = 1 if args.kind in {"lowpass", "highpass"} else 2
    if len(args.fp) != edges or len(args.fs) != edges:
        raise SystemExit(f"{args.kind} needs {edges} value(s) for --fp and --fs.")
    if edges == 1:
        spec.update(fp=args.fp[0], fs=args.fs[0])
    else:
        spec.update(fp1=args.fp[0], fp2=args.fp[1], fs1=args.fs[0], fs2=args.fs[1])
    return spec


def find_simulator(explicit: str | None = None) -> Path | None:
    for candidate in (explicit, os.environ.get("SOFIA_SPICE")):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    for candidate in LTSPICE_CANDIDATES:
        if Path(candidate).exists():
            return Path(candidate)
    for name in ("ngspice", "ngspice_con"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def _is_ngspice(simulator: Path) -> bool:
    return "ngspice" in simulator.name.lower()


def spec_bands(spec: dict[str, Any]) -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """Return (passbands, stopbands) as frequency intervals in Hz."""
    kind = spec["kind"]
    if kind == "lowpass":
        fp, fs = float(spec["fp"]), float(spec["fs"])
        return [(fp / 100, fp)], [(fs, fs * 10)]
    if kind == "highpass":
        fp, fs = float(spec["fp"]), float(spec["fs"])
        return [(fp, fp * 10)], [(fs / 10, fs)]
    fp1, fp2 = float(spec["fp1"]), float(spec["fp2"])
    fs1, fs2 = float(spec["fs1"]), float(spec["fs2"])
    if kind == "bandpass":
        return [(fp1, fp2)], [(fs1 / 10, fs1), (fs2, fs2 * 10)]
    if kind == "bandstop":
        return [(fp1 / 10, fp1), (fp2, fp2 * 10)], [(fs1, fs2)]
    raise ValueError(f"Unknown filter kind: {kind}")


def sweep_limits(spec: dict[str, Any]) -> tuple[float, float]:
    passbands, stopbands = spec_bands(spec)
    edges = [edge for band in passbands + stopbands for edge in band]
    return min(edges) / 2, max(edges) * 2


def _resolve_include(target: str, netlist_dir: Path) -> Path | None:
    raw = Path(target.strip())
    for candidate in (raw, netlist_dir / raw, ROOT / raw):
        if candidate.exists():
            return candidate.absolute()
    # A netlist moved to another folder: fall back to the bundled model with the same file name.
    name = re.split(r"[\\/]", target.strip())[-1].lower()
    for model in MODELS_DIR.glob("*.cir"):
        if model.name.lower() == name:
            return model.absolute()
    return None


def _ideal_opamp_lines(netlist_lines: list[str]) -> list[str]:
    """Ideal op amp (VCVS, gain 1e6) for every subcircuit the netlist instantiates but does not define."""
    defined = {line.split()[1].upper() for line in netlist_lines if line.lower().startswith(".subckt")}
    used: list[str] = []
    for line in netlist_lines:
        parts = line.split()
        if parts and parts[0][:1].upper() == "X" and len(parts) >= 7:
            name = parts[-1]
            if name.upper() not in defined and name not in used:
                used.append(name)
    lines: list[str] = []
    for name in used:
        lines.extend([f".subckt {name} 1 2 3 4 5", "E1 5 0 1 2 1e6", ".ends"])
    return lines


def prepare_netlist(source: Path, destination: Path, f_start: float, f_stop: float, ideal_opamp: bool = False) -> list[str]:
    """Copy a netlist with absolute includes and a known AC sweep. Returns problems found."""
    problems: list[str] = []
    lines = [f"* Prepared for simulation from {source.name}"]
    for raw_line in source.read_text(encoding="utf-8", errors="replace").splitlines():
        include = INCLUDE_RE.match(raw_line)
        if include:
            if ideal_opamp:
                continue
            resolved = _resolve_include(include.group(2), source.parent)
            if resolved is None:
                problems.append(f"Include not found: {include.group(2)}")
                lines.append(raw_line)
            else:
                lines.append(f'.include "{resolved}"')
            continue
        if DROP_RE.match(raw_line):
            continue
        lines.append(raw_line)
    if ideal_opamp:
        lines.extend(_ideal_opamp_lines(lines))
    lines.append(f".ac dec 200 {f_start:.6g} {f_stop:.6g}")
    lines.append(".end")
    destination.write_text("\n".join(lines) + "\n", encoding="ascii", errors="replace")
    return problems


def _read_text_any(path: Path) -> str:
    data = path.read_bytes()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff") or b"\x00" in data[:200]:
        return data.decode("utf-16", errors="replace").lstrip("\ufeff")
    return data.decode("latin-1")


def parse_ascii_raw(path: Path) -> dict[str, list[complex]]:
    text = _read_text_any(path)
    header, _, values = text.partition("Values:")
    names: list[str] = []
    in_vars = False
    for line in header.splitlines():
        if line.strip().lower().startswith("variables:"):
            in_vars = True
            continue
        if in_vars:
            parts = line.split()
            if len(parts) >= 2 and parts[0].isdigit():
                names.append(parts[1].lower())
    if not names:
        raise ValueError(f"No variables found in {path.name} (empty simulation output)")
    tokens = values.split()
    width = len(names) + 1
    data: dict[str, list[complex]] = {name: [] for name in names}
    for start in range(0, len(tokens) - width + 1, width):
        for name, token in zip(names, tokens[start + 1 : start + width]):
            real, _, imag = token.partition(",")
            data[name].append(complex(float(real), float(imag or 0.0)))
    return data


def run_simulator(simulator: Path, netlist: Path) -> tuple[Path, str]:
    raw = netlist.with_suffix(".raw")
    if _is_ngspice(simulator):
        env = dict(os.environ, SPICE_ASCIIRAWFILE="1")
        cmd = [str(simulator), "-b", "-r", str(raw), str(netlist)]
    else:
        env = dict(os.environ)
        cmd = [str(simulator), "-b", "-ascii", str(netlist)]
    completed = subprocess.run(cmd, cwd=netlist.parent, env=env, capture_output=True, text=True, timeout=300)
    log_path = netlist.with_suffix(".log")
    log = _read_text_any(log_path) if log_path.exists() else ""
    log += completed.stdout + completed.stderr
    if not raw.exists():
        raise RuntimeError(f"Simulator produced no raw file. Log:\n{log.strip()}")
    return raw, log


def _interp_db(freqs: list[float], gains: list[float], target: float) -> float:
    if target <= freqs[0]:
        return gains[0]
    if target >= freqs[-1]:
        return gains[-1]
    for index in range(1, len(freqs)):
        if freqs[index] >= target:
            f0, f1 = math.log10(freqs[index - 1]), math.log10(freqs[index])
            t = (math.log10(target) - f0) / (f1 - f0) if f1 > f0 else 0.0
            return gains[index - 1] + t * (gains[index] - gains[index - 1])
    return gains[-1]


def _band_values(freqs: list[float], gains: list[float], band: tuple[float, float]) -> list[tuple[float, float]]:
    low, high = band
    points = [(f, g) for f, g in zip(freqs, gains) if low <= f <= high]
    points.append((low, _interp_db(freqs, gains, low)))
    points.append((high, _interp_db(freqs, gains, high)))
    return points


def evaluate_response(
    freqs: list[float],
    gains_db: list[float],
    spec: dict[str, Any],
    ripple_tol: float,
    atten_tol: float,
) -> dict[str, Any]:
    ap = float(spec["ap"])
    a_stop = float(spec["as"])
    passbands, stopbands = spec_bands(spec)
    pass_points = [point for band in passbands for point in _band_values(freqs, gains_db, band)]
    stop_points = [point for band in stopbands for point in _band_values(freqs, gains_db, band)]
    pass_max = max(gain for _, gain in pass_points)
    pass_min_f, pass_min = min(pass_points, key=lambda point: point[1])
    stop_max_f, stop_max = max(stop_points, key=lambda point: point[1])
    ripple = pass_max - pass_min
    attenuation = pass_max - stop_max
    ripple_ok = ripple <= ap + ripple_tol
    atten_ok = attenuation >= a_stop - atten_tol
    if ripple <= ap + 1e-6 and attenuation >= a_stop - 1e-6:
        verdict = "cumple"
    elif ripple_ok and atten_ok:
        verdict = "cumple_con_tolerancia"
    else:
        verdict = "no_cumple"
    return {
        "verdict": verdict,
        "passband_gain_db": round(pass_max, 4),
        "passband_ripple_db": round(ripple, 4),
        "passband_ripple_limit_db": ap,
        "passband_worst_hz": round(pass_min_f, 3),
        "stopband_attenuation_db": round(attenuation, 4),
        "stopband_attenuation_required_db": a_stop,
        "stopband_worst_hz": round(stop_max_f, 3),
        "ripple_ok": ripple_ok,
        "attenuation_ok": atten_ok,
        "passbands_hz": passbands,
        "stopbands_hz": stopbands,
    }


def simulated_response(
    simulator: Path,
    netlist: Path,
    spec: dict[str, Any],
    output_node: str = "OUT",
    ideal_opamp: bool = False,
) -> tuple[list[float], list[float]]:
    """AC sweep of a netlist over the spec's range: (frequencies in Hz, gain in dB)."""
    f_start, f_stop = sweep_limits(spec)
    with tempfile.TemporaryDirectory(prefix="sofia_sim_") as tmp:
        prepared = Path(tmp) / "case.cir"
        prepare_netlist(netlist, prepared, f_start, f_stop, ideal_opamp)
        raw, _ = run_simulator(simulator, prepared)
        data = parse_ascii_raw(raw)
    probe = f"v({output_node.lower()})"
    freqs = [abs(value) for value in data["frequency"]]
    return freqs, [20 * math.log10(max(abs(value), 1e-30)) for value in data[probe]]


def simulate_netlist(
    simulator: Path,
    netlist: Path,
    spec: dict[str, Any],
    output_node: str,
    ripple_tol: float,
    atten_tol: float,
    ideal_opamp: bool = False,
) -> dict[str, Any]:
    if not netlist.exists():
        return {"present": False}
    f_start, f_stop = sweep_limits(spec)
    with tempfile.TemporaryDirectory(prefix="sofia_sim_") as tmp:
        prepared = Path(tmp) / "case.cir"
        problems = prepare_netlist(netlist, prepared, f_start, f_stop, ideal_opamp)
        try:
            raw, log = run_simulator(simulator, prepared)
            data = parse_ascii_raw(raw)
        except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
            return {"present": True, "verdict": "error_simulacion", "problems": problems, "error": str(exc)[-2000:]}
    probe = f"v({output_node.lower()})"
    if probe not in data:
        return {
            "present": True,
            "verdict": "error_simulacion",
            "problems": problems,
            "error": f"Node {output_node} not found. Available: {sorted(data)}",
        }
    freqs = [abs(value) for value in data["frequency"]]
    gains = [20 * math.log10(max(abs(value), 1e-30)) for value in data[probe]]
    metrics = evaluate_response(freqs, gains, spec, ripple_tol, atten_tol)
    warnings = [line.strip() for line in log.splitlines() if re.search(r"warning|error|singular|fail", line, re.I)]
    step = max(1, len(freqs) // 120)
    return {
        "present": True,
        "output_node": output_node,
        **metrics,
        "problems": problems,
        "simulator_messages": warnings[:20],
        "response_db": [[round(f, 4), round(g, 4)] for f, g in zip(freqs[::step], gains[::step])],
    }


def diagnose(real: dict[str, Any], ideal: dict[str, Any]) -> str:
    real_ok = real.get("verdict") in {"cumple", "cumple_con_tolerancia"}
    ideal_ok = ideal.get("verdict") in {"cumple", "cumple_con_tolerancia"}
    if real.get("verdict") == "error_simulacion":
        return "no_simula"
    if real_ok:
        return "funciona"
    if ideal_ok:
        return "limitacion_del_opamp"
    return "error_de_diseno"


def main() -> int:
    args = build_parser().parse_args()
    simulator = find_simulator(args.spice)
    if simulator is None:
        raise SystemExit("No SPICE simulator found. Install LTspice or ngspice, or pass --spice / set SOFIA_SPICE.")
    netlist = Path(args.netlist)
    if not netlist.exists():
        raise SystemExit(f"Netlist not found: {netlist}")
    spec = spec_from_args(args)
    real = simulate_netlist(simulator, netlist, spec, args.output_node, args.ripple_tol, args.atten_tol)
    ideal = simulate_netlist(simulator, netlist, spec, args.output_node, args.ripple_tol, args.atten_tol, ideal_opamp=True)
    for result in (real, ideal):
        result.pop("response_db", None)
    print(json.dumps({"real": real, "ideal_opamp": ideal, "diagnosis": diagnose(real, ideal)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
