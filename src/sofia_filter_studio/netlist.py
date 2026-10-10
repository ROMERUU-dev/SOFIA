from __future__ import annotations

import os
import sys
from pathlib import Path

from .circuit import CAPACITOR, OPAMP, Part, StageCircuit, build_circuit
from .models import DesignInputs, DesignResult, FilterKind, Stage, Topology


MODEL_FILE_MAP = {
    "LM324": "oplm324.cir",
    "LM318": "LM318.cir",
    "uA741": "ua741.cir",
    "TL082": "TL082.cir",
    "LM7171": "LM7171.cir",
    "LM6164": "LM6164.cir",
    "LM6165": "LM6165.cir",
    "LM6171": "LM6171.cir",
}

# Subcircuit names as declared inside the vendor model files.
MODEL_SUBCKT_MAP = {
    "LM7171": "LM7171B/NS",
    "LM6164": "LM6164/NS",
    "LM6165": "LM6165/NS",
    "LM6171": "LM6171A/NS",
}

# Single-supply rail per op amp. The virtual ground sits at half the rail, which keeps it inside
# every model's input common-mode range (TL082/uA741/LM7171 do not bias with a 5 V rail).
DEFAULT_SUPPLY_V = 15.0
SUPPLY_VOLTAGE_MAP = {"LM324": 5.0}

# Models whose DC solution the .nodeset hint makes worse: with it LTspice never finds the operating
# point of many LM7171/LM6171 designs (and one LM6165 design), while TL082 and uA741 need it.
NO_NODESET_MODELS = {"LM7171", "LM6171", "LM6165"}

def _models_dir() -> Path:
    # Inside a PyInstaller bundle the models travel next to the extracted package.
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "resources" / "models"
    return Path(__file__).absolute().parents[2] / "resources" / "models"


MODELS_DIR = _models_dir()


def model_path_for(inputs: DesignInputs) -> Path:
    filename = MODEL_FILE_MAP[inputs.opamp.value]
    return Path("resources") / "models" / filename


def subckt_name_for(inputs: DesignInputs) -> str:
    return MODEL_SUBCKT_MAP.get(inputs.opamp.value, inputs.opamp.value)


def supply_voltage_for(inputs: DesignInputs) -> float:
    return SUPPLY_VOLTAGE_MAP.get(inputs.opamp.value, DEFAULT_SUPPLY_V)


def _include_path(inputs: DesignInputs, netlist_path: Path | None) -> str:
    model = MODELS_DIR / MODEL_FILE_MAP[inputs.opamp.value]
    if netlist_path is None or not model.exists():
        return model_path_for(inputs).as_posix()
    try:
        return Path(os.path.relpath(model, Path(netlist_path).absolute().parent)).as_posix()
    except ValueError:
        # Different drive on Windows: fall back to an absolute path.
        return model.as_posix()


def ac_sweep_limits(inputs: DesignInputs) -> tuple[float, float]:
    edges: list[float] = []
    for value in (inputs.spec.passband_hz, inputs.spec.stopband_hz):
        edges.extend(value if isinstance(value, tuple) else (value,))
    return min(edges) / 10, max(edges) * 10


def _stage_comment(stage: Stage, kind: FilterKind) -> str:
    q_text = f"{stage.q:.5f}" if stage.q is not None else "first-order"
    return f"* Stage {stage.index}: {kind.value}, f0={stage.natural_frequency_hz:.5f} Hz, Q={q_text}, order={stage.order}"


def _part_line(part: Part, subckt: str) -> str:
    if part.kind == OPAMP:
        plus, minus, out = part.nodes
        return f"{part.name} {plus} {minus} VCC 0 {out} {subckt}"
    if part.kind == CAPACITOR:
        return f"{part.name} {part.nodes[0]} {part.nodes[1]} {part.value:.9e}"
    return f"{part.name} {part.nodes[0]} {part.nodes[1]} {part.value:.6f}"


def model_text_for(inputs: DesignInputs) -> str:
    return (MODELS_DIR / MODEL_FILE_MAP[inputs.opamp.value]).read_text(encoding="latin-1")


def render_netlist(
    inputs: DesignInputs,
    result: DesignResult,
    netlist_path: Path | None = None,
    inline_model: bool = False,
    exact_values: bool = False,
) -> str:
    """Render the SPICE netlist.

    With ``inline_model`` the op amp subcircuit is embedded instead of referenced with ``.include``,
    so the file opens anywhere (this is what the original SOFIA editor did by pasting the model).
    With ``exact_values`` every resistor gets its ideal (target) value instead of the commercial one;
    used to verify that the circuit realizes the designed transfer function.
    """
    supply = supply_voltage_for(inputs)
    vref = supply / 2
    lines: list[str] = []
    lines.append("* SOFIA Filter Studio generated netlist")
    lines.append(f"* Topology request: {inputs.topology.value}")
    lines.append(f"* Filter kind: {inputs.kind.value}")
    lines.append(f"* Approximation: {inputs.approximation.value}")
    lines.append(f"* Filter order: {result.order}")
    lines.append(f"* Epsilon: {result.epsilon:.8f}")
    if not inline_model:
        lines.append(f'.include "{_include_path(inputs, netlist_path)}"')
    lines.append("")
    lines.append(f"* polarizacion de tierra virtual: fuente unica de {supply:g} V, tierra virtual en {vref:g} V")
    lines.append(f"Vin IN 0 DC {vref:g} AC 1")
    lines.append(f"VTIERRA VREF 0 {vref:g}V")
    lines.append(f"VCC VCC 0 DC {supply:g}")
    lines.append("RLOAD OUT 0 100k")
    lines.append("")

    if inputs.topology is Topology.OTA:
        lines.append("* OTA flow migrated as a parameterized placeholder.")
        lines.append(f".param C1={inputs.stage_capacitor_f:.9e}")
        lines.append("* TODO: port legacy OTA sizing equations and transistor-level export.")
    else:
        subckt = subckt_name_for(inputs)
        circuit = build_circuit(inputs, result, exact_values)
        for stage_circuit in circuit:
            lines.append(_stage_comment(stage_circuit.stage, inputs.kind))
            lines.extend(item if isinstance(item, str) else _part_line(item, subckt) for item in stage_circuit.items)
            lines.append("")
        if inputs.opamp.value not in NO_NODESET_MODELS:
            lines.extend(_nodeset_lines(circuit, vref))

    if inline_model:
        lines.append(f"* Modelo del opamp {inputs.opamp.value} ({MODEL_FILE_MAP[inputs.opamp.value]})")
        lines.extend(model_text_for(inputs).strip().splitlines())
        lines.append("")

    f_start, f_stop = ac_sweep_limits(inputs)
    lines.append(f".ac dec 100 {f_start:.6g} {f_stop:.6g}")
    lines.append(".probe V(OUT)")
    lines.append(".end")
    return "\n".join(lines)


def _nodeset_lines(circuit: list[StageCircuit], vref: float, per_line: int = 8) -> list[str]:
    """Seed every op amp output at the virtual ground.

    Op amp macro-models (TL082 in particular) admit a latched DC solution with the output stuck at a
    rail; without a hint the simulator can converge there and the AC result becomes meaningless.
    Seeding only the outputs is enough; seeding every node makes some Tow-Thomas cascades diverge.
    """
    nodes: list[str] = []
    for stage_circuit in circuit:
        for part in stage_circuit.parts:
            if part.kind == OPAMP and part.nodes[2] not in nodes:
                nodes.append(part.nodes[2])
    if not nodes:
        return []
    lines = ["* punto de operacion inicial en la tierra virtual"]
    for start in range(0, len(nodes), per_line):
        chunk = " ".join(f"V({node})={vref:g}" for node in nodes[start : start + per_line])
        lines.append(f".nodeset {chunk}" if start == 0 else f"+ {chunk}")
    lines.append("")
    return lines
