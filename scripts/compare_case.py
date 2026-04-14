from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_DIR = ROOT / "docs" / "benchmark"


COMPONENT_RE = re.compile(r"^(?P<name>[A-Za-z][A-Za-z0-9_]*|\w+)\s+(?P<body>.+)$")
NUMBER_RE = re.compile(
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)(?P<suffix>Meg|[fpnumkKMGT]?)"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare one SOFIA benchmark case.")
    parser.add_argument("case_dir", help="Path or case id inside docs/benchmark.")
    parser.add_argument("--write-markdown", action="store_true", help="Also write comparison.md.")
    return parser


def resolve_case_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if path.exists():
        return path.resolve()
    return (BENCHMARK_DIR / value).resolve()


def load_json(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        payload, _ = json.JSONDecoder().raw_decode(text)
        return payload


def parse_numeric_token(token: str) -> float | None:
    match = NUMBER_RE.fullmatch(token.strip())
    if not match:
        return None
    value = float(match.group("value"))
    suffix = match.group("suffix")
    scale = {
        "f": 1e-15,
        "p": 1e-12,
        "n": 1e-9,
        "u": 1e-6,
        "m": 1e-3,
        "k": 1e3,
        "K": 1e3,
        "Meg": 1e6,
        "M": 1e6,
        "G": 1e9,
        "T": 1e12,
    }.get(suffix, 1.0)
    return value * scale


def summarize_netlist(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"present": False}

    components: list[dict[str, Any]] = []
    includes: list[str] = []
    analyses: list[str] = []

    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("*"):
            continue
        lower = line.lower()
        if lower.startswith(".include"):
            includes.append(line)
            continue
        if lower.startswith(".ac") or lower.startswith(".tran") or lower.startswith(".dc"):
            analyses.append(line)
            continue
        if line.startswith("."):
            continue

        match = COMPONENT_RE.match(line)
        if not match:
            continue
        name = match.group("name")
        tokens = match.group("body").split()
        numeric_values = [value for token in tokens if (value := parse_numeric_token(token)) is not None]
        components.append(
            {
                "name": name,
                "kind": name[0].upper(),
                "line": line,
                "numeric_values": numeric_values,
            }
        )

    counts: dict[str, int] = {}
    for component in components:
        counts[component["kind"]] = counts.get(component["kind"], 0) + 1

    return {
        "present": True,
        "component_count": len(components),
        "component_counts_by_prefix": counts,
        "includes": includes,
        "analyses": analyses,
        "components": components,
    }


def summarize_result(result: dict[str, Any]) -> dict[str, Any]:
    stages = result.get("stages", [])
    return {
        "order": result.get("order"),
        "stage_count": len(stages),
        "stage_q": [stage.get("q") for stage in stages],
        "stage_f0_hz": [stage.get("natural_frequency_hz") for stage in stages],
        "summary": result.get("summary", {}),
        "warnings": result.get("warnings", []),
    }


def compare(case_dir: Path) -> dict[str, Any]:
    result_path = case_dir / "result.json"
    generated_path = case_dir / "generated.cir"
    legacy_path = case_dir / "legacy.cir"

    if not result_path.exists():
        raise SystemExit(f"Missing result.json in {case_dir}")
    if not generated_path.exists():
        raise SystemExit(f"Missing generated.cir in {case_dir}")

    result = load_json(result_path)
    modern_netlist = summarize_netlist(generated_path)
    legacy_netlist = summarize_netlist(legacy_path)

    checks: list[dict[str, Any]] = []
    checks.append(
        {
            "name": "legacy_netlist_present",
            "status": "pass" if legacy_netlist["present"] else "pending",
            "detail": "legacy.cir is present" if legacy_netlist["present"] else "Capture legacy.cir from SOFIA original on Windows.",
        }
    )
    checks.append(
        {
            "name": "modern_netlist_present",
            "status": "pass" if modern_netlist["present"] else "fail",
            "detail": "generated.cir is present",
        }
    )

    if legacy_netlist["present"]:
        modern_counts = modern_netlist["component_counts_by_prefix"]
        legacy_counts = legacy_netlist["component_counts_by_prefix"]
        checks.append(
            {
                "name": "component_prefix_counts",
                "status": "review" if modern_counts != legacy_counts else "pass",
                "modern": modern_counts,
                "legacy": legacy_counts,
            }
        )

    if any(check["status"] == "fail" for check in checks):
        status = "fail"
    elif any(check["status"] == "pending" for check in checks):
        status = "pending_legacy"
    elif any(check["status"] == "review" for check in checks):
        status = "needs_review"
    else:
        status = "equivalent_structure"

    return {
        "case_id": case_dir.name,
        "status": status,
        "modern_result": summarize_result(result),
        "modern_netlist": modern_netlist,
        "legacy_netlist": legacy_netlist,
        "checks": checks,
    }


def write_markdown(case_dir: Path, payload: dict[str, Any]) -> None:
    modern = payload["modern_result"]
    lines = [
        f"# Comparison: {payload['case_id']}",
        "",
        f"- status: `{payload['status']}`",
        f"- modern order: `{modern['order']}`",
        f"- modern stages: `{modern['stage_count']}`",
        "",
        "## Checks",
        "",
    ]
    for check in payload["checks"]:
        lines.append(f"- `{check['name']}`: `{check['status']}`")
    lines.append("")
    (case_dir / "comparison.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = build_parser().parse_args()
    case_dir = resolve_case_dir(args.case_dir)
    payload = compare(case_dir)
    (case_dir / "comparison.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    if args.write_markdown:
        write_markdown(case_dir, payload)
    print(json.dumps({"case_id": payload["case_id"], "status": payload["status"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
