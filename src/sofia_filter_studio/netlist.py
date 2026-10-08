from __future__ import annotations

import os
import sys
from pathlib import Path

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


def _format_resistor_network(name: str, node_a: str, node_b: str, realized_name: str, network) -> list[str]:
    if network.connection == "single":
        return [f"{realized_name} {node_a} {node_b} {network.realized_ohms:.6f}"]

    midpoint = f"{realized_name}_MID"
    lines = [f"* {name}: {network.connection} array for target {network.target_ohms:.6f} ohm"]
    if network.connection == "series":
        current_a = node_a
        for index, value in enumerate(network.parts_ohms, start=1):
            current_b = node_b if index == len(network.parts_ohms) else f"{midpoint}{index}"
            lines.append(f"{realized_name}_{index} {current_a} {current_b} {value:.6f}")
            current_a = current_b
        return lines

    for index, value in enumerate(network.parts_ohms, start=1):
        lines.append(f"{realized_name}_{index} {node_a} {node_b} {value:.6f}")
    return lines


def _stage_ports(stage: Stage, total_stages: int) -> tuple[str, str]:
    stage_input = "IN" if stage.index == 1 else f"1{stage.index - 1}"
    stage_output = "OUT" if stage.index == total_stages else f"1{stage.index}"
    return stage_input, stage_output


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
        total_stages = len(result.stages)
        stage_lines: list[str] = []
        for stage in result.stages:
            stage_lines.append(_stage_comment(stage, inputs.kind))
            stage_lines.extend(_render_stage_template(inputs, stage, total_stages, exact_values))
            stage_lines.append("")
        lines.extend(stage_lines)
        lines.extend(_nodeset_lines(stage_lines, vref))

    if inline_model:
        lines.append(f"* Modelo del opamp {inputs.opamp.value} ({MODEL_FILE_MAP[inputs.opamp.value]})")
        lines.extend(model_text_for(inputs).strip().splitlines())
        lines.append("")

    f_start, f_stop = ac_sweep_limits(inputs)
    lines.append(f".ac dec 100 {f_start:.6g} {f_stop:.6g}")
    lines.append(".probe V(OUT)")
    lines.append(".end")
    return "\n".join(lines)


def _nodeset_lines(stage_lines: list[str], vref: float, per_line: int = 8) -> list[str]:
    """Seed every op amp output at the virtual ground.

    Op amp macro-models (TL082 in particular) admit a latched DC solution with the output stuck at a
    rail; without a hint the simulator can converge there and the AC result becomes meaningless.
    Seeding only the outputs is enough; seeding every node makes some Tow-Thomas cascades diverge.
    """
    nodes: list[str] = []
    for line in stage_lines:
        parts = line.split()
        if len(parts) >= 7 and parts[0].upper().startswith("X"):
            output = parts[-2]
            if output not in nodes:
                nodes.append(output)
    if not nodes:
        return []
    lines = ["* punto de operacion inicial en la tierra virtual"]
    for start in range(0, len(nodes), per_line):
        chunk = " ".join(f"V({node})={vref:g}" for node in nodes[start : start + per_line])
        lines.append(f".nodeset {chunk}" if start == 0 else f"+ {chunk}")
    lines.append("")
    return lines


class _StageWriter:
    """Small helper that emits the element lines of one stage with legacy-style names."""

    def __init__(self, inputs: DesignInputs, stage: Stage, exact_values: bool = False) -> None:
        self.inputs = inputs
        self.stage = stage
        self.realization = stage.realization
        self.subckt = subckt_name_for(inputs)
        self.exact_values = exact_values
        self.lines: list[str] = []

    def node(self, prefix: int) -> str:
        return f"{prefix}{self.stage.index}"

    def opamp(self, number: int, plus: str, minus: str, out: str) -> None:
        self.lines.append(f"Xao{number}{self.stage.index} {plus} {minus} VCC 0 {out} {self.subckt}")

    def cap(self, number: int, node_a: str, node_b: str, key: str) -> None:
        value = self.realization.capacitor_values_f[key]
        self.lines.append(f"c{number}{self.stage.index} {node_a} {node_b} {value:.9e}")

    def res(self, number: int, node_a: str, node_b: str, key: str) -> None:
        network = self.realization.resistor_networks[key]
        name = f"r{number}{self.stage.index}"
        if self.exact_values:
            self.lines.append(f"{name} {node_a} {node_b} {network.target_ohms:.6f}")
            return
        self.lines.extend(_format_resistor_network(key, node_a, node_b, name, network))

    def has(self, key: str) -> bool:
        return key in self.realization.resistor_networks or key in self.realization.capacitor_values_f


def _render_stage_template(inputs: DesignInputs, stage: Stage, total_stages: int, exact_values: bool = False) -> list[str]:
    realization = stage.realization
    stage_input, stage_output = _stage_ports(stage, total_stages)
    lines = [f"* Stage input: {stage_input}", f"* Stage output: {stage_output}"]
    if realization is None:
        lines.append("* Missing realization")
        return lines
    for note in realization.notes:
        lines.append(f"* {note}")

    writer = _StageWriter(inputs, stage, exact_values)
    topology = realization.topology
    if stage.order == 1:
        if topology in {Topology.MFB, Topology.TOW_THOMAS}:
            _render_first_order_inverting(writer, inputs.kind, stage_input, stage_output)
        else:
            _render_first_order_follower(writer, inputs.kind, stage_input, stage_output)
    elif topology is Topology.SALLEN_KEY:
        _render_sallen_key(writer, inputs.kind, stage_input, stage_output)
    elif topology is Topology.MFB:
        _render_mfb(writer, inputs.kind, stage_input, stage_output)
    elif topology is Topology.TOW_THOMAS:
        _render_tow_thomas(writer, inputs.kind, stage_input, stage_output)
    elif topology is Topology.ANTONIOU:
        _render_antoniou(writer, inputs.kind, stage_input, stage_output)
    else:
        writer.lines.append("* Unknown topology")
    return lines + writer.lines


def _render_first_order_follower(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2 = w.node(2)
    w.opamp(1, n2, out_node, out_node)
    if kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.res(1, n2, "VREF", "R1")
    else:
        w.res(1, in_node, n2, "R1")
        w.cap(1, n2, "VREF", "C1")


def _render_first_order_inverting(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2, n3 = w.node(2), w.node(3)
    w.opamp(1, "VREF", n3, out_node)
    if kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.res(1, n2, n3, "R1")
    else:
        w.res(1, in_node, n3, "R1")
        w.cap(1, n3, out_node, "C1")
    w.res(2, n3, out_node, "R2")


def _render_sallen_key(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2, n3, n4 = w.node(2), w.node(3), w.node(4)
    unity = not w.has("Rf")
    w.opamp(1, n3, out_node if unity else n4, out_node)
    if kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.cap(2, n2, n3, "C2")
        w.res(3, n2, out_node, "R1")
        w.res(4, n3, "VREF", "R2")
    elif kind is FilterKind.BANDPASS:
        if w.has("R1a"):
            w.res(3, in_node, n2, "R1a")
            w.res(6, n2, "VREF", "R1b")
        else:
            w.res(3, in_node, n2, "R1")
        w.cap(1, n2, "VREF", "C1")
        w.cap(2, n2, n3, "C2")
        w.res(4, n2, out_node, "R2")
        w.res(5, n3, "VREF", "R3")
    else:
        w.cap(1, n3, "VREF", "C1")
        w.cap(2, n2, out_node, "C2")
        w.res(3, in_node, n2, "R1")
        w.res(4, n2, n3, "R2")
    if not unity:
        w.res(1, n4, "VREF", "Rg")
        w.res(2, n4, out_node, "Rf")


def _render_mfb(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2, n3 = w.node(2), w.node(3)
    w.opamp(1, "VREF", n3, out_node)
    if kind is FilterKind.BANDPASS:
        w.cap(1, n2, n3, "C1")
        w.cap(2, n2, out_node, "C2")
        w.res(1, n3, out_node, "R1")
        if w.has("R2"):
            w.res(2, n2, "VREF", "R2")
        w.res(3, in_node, n2, "R3")
    elif kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.cap(2, n2, out_node, "C2")
        w.cap(3, n2, n3, "C3")
        w.res(1, n2, "VREF", "R1")
        w.res(2, n3, out_node, "R2")
    else:
        w.cap(1, n2, "VREF", "C1")
        w.cap(2, n3, out_node, "C2")
        w.res(1, in_node, n2, "R1")
        w.res(2, n2, out_node, "R2")
        w.res(3, n2, n3, "R3")


def _render_tow_thomas(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2, n4, n6, n7 = w.node(2), w.node(4), w.node(6), w.node(7)
    if kind is FilterKind.LOWPASS:
        bandpass_node, lowpass_node = w.node(3), out_node
    else:
        bandpass_node, lowpass_node = out_node, w.node(5)
    w.opamp(1, "VREF", n2, bandpass_node)
    w.opamp(2, "VREF", n4, lowpass_node)
    w.opamp(3, "VREF", n6, n7)
    w.cap(1, n2, bandpass_node, "C1")
    w.cap(2, n4, lowpass_node, "C2")
    w.res(2, n7, n2, "R")
    w.res(3, bandpass_node, n4, "R")
    w.res(4, n2, bandpass_node, "Rq")
    w.res(5, lowpass_node, n6, "Rinv")
    w.res(6, n6, n7, "Rinv")
    if w.has("R1"):
        w.res(1, in_node, n2, "R1")
    if w.has("Cff"):
        w.cap(3, in_node, n2, "Cff")
    if w.has("Rff"):
        w.res(7, in_node, n4, "Rff")


def _render_antoniou(w: _StageWriter, kind: FilterKind, in_node: str, out_node: str) -> None:
    # GIC nodes: X=n6 (simulated inductor), a=n5, b=n4, c=n3, d=n2.
    n2, n3, n4, n5, n6, n7 = w.node(2), w.node(3), w.node(4), w.node(5), w.node(6), w.node(7)
    w.opamp(1, n2, n4, n5)
    w.opamp(2, n6, n4, n3)
    if w.has("Rf"):
        w.opamp(3, n6, n7, out_node)
        w.res(8, n7, "VREF", "Rg")
        w.res(9, n7, out_node, "Rf")
    else:
        w.opamp(3, n6, out_node, out_node)
    w.res(1, n5, n6, "R")
    w.res(2, n4, n5, "R")
    w.res(3, n3, n4, "R")
    w.cap(4, n2, n3, "C1")
    if w.has("R5"):
        lifted = kind in {FilterKind.LOWPASS, FilterKind.BANDSTOP}
        w.res(5, n2, in_node if lifted else "VREF", "R5")
    if w.has("R5a"):
        w.res(5, n2, in_node, "R5a")
        w.res(7, n2, "VREF", "R5b")
    if w.has("C2"):
        w.cap(6, n6, in_node if kind is FilterKind.HIGHPASS else "VREF", "C2")
    if w.has("C2a"):
        w.cap(6, n6, in_node, "C2a")
    if w.has("C2b"):
        w.cap(7, n6, "VREF", "C2b")
    w.res(6, n6, in_node if kind is FilterKind.BANDPASS else "VREF", "Rq")
