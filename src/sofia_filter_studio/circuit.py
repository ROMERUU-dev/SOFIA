"""The designed filter as a list of parts with their nodes.

The SPICE netlist, the schematic, the bill of materials and the PCB are all generated from this, so
they always describe the same circuit. Node names are the netlist ones: ``IN``, ``OUT``, ``VREF``
(virtual ground), ``1<k>`` between stage k and k+1, and ``<n><k>`` inside stage k.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import DesignInputs, DesignResult, FilterKind, Stage, Topology

RESISTOR, CAPACITOR, OPAMP = "R", "C", "U"


@dataclass(slots=True)
class Part:
    """One resistor, capacitor or op amp section.

    ``nodes`` is (a, b) for resistors and capacitors and (non-inverting, inverting, output) for an op
    amp section, whose supply pins go to VCC and ground. ``role`` names the same nodes inside the
    stage: ``in``, ``out``, ``vref`` or ``n<k>``; the schematic templates are drawn in those terms.
    """

    name: str
    kind: str
    nodes: tuple[str, ...]
    stage: int
    key: str | None = None
    value: float | None = None
    target: float | None = None
    role: tuple[str, ...] = ()


@dataclass(slots=True)
class StageCircuit:
    stage: Stage
    topology: Topology
    input: str
    output: str
    # Parts in netlist order; plain strings are comment lines kept for the netlist.
    items: list[Part | str] = field(default_factory=list)

    @property
    def parts(self) -> list[Part]:
        return [item for item in self.items if isinstance(item, Part)]

    def part(self, key: str) -> Part | None:
        return next((part for part in self.parts if part.key == key), None)


def stage_ports(stage: Stage, total_stages: int) -> tuple[str, str]:
    stage_input = "IN" if stage.index == 1 else f"1{stage.index - 1}"
    stage_output = "OUT" if stage.index == total_stages else f"1{stage.index}"
    return stage_input, stage_output


def build_circuit(inputs: DesignInputs, result: DesignResult, exact_values: bool = False) -> list[StageCircuit]:
    """One StageCircuit per stage. ``exact_values`` puts the ideal value in every resistor."""
    total = len(result.stages)
    return [_build_stage(inputs, stage, total, exact_values) for stage in result.stages]


class _StageBuilder:
    """Adds the parts of one stage with the legacy element names (r<number><stage>, ...)."""

    def __init__(self, inputs: DesignInputs, stage: Stage, circuit: StageCircuit, exact_values: bool) -> None:
        self.inputs = inputs
        self.stage = stage
        self.realization = stage.realization
        self.circuit = circuit
        self.exact_values = exact_values
        index = str(stage.index)
        self.roles = {circuit.input: "in", circuit.output: "out", "VREF": "vref"}
        for prefix in range(2, 10):
            self.roles.setdefault(f"{prefix}{index}", f"n{prefix}")

    def node(self, prefix: int) -> str:
        return f"{prefix}{self.stage.index}"

    def _add(self, part: Part) -> None:
        part.role = tuple(self.roles.get(node, node) for node in part.nodes)
        self.circuit.items.append(part)

    def opamp(self, number: int, plus: str, minus: str, out: str) -> None:
        self._add(Part(f"Xao{number}{self.stage.index}", OPAMP, (plus, minus, out), self.stage.index))

    def cap(self, number: int, node_a: str, node_b: str, key: str) -> None:
        value = self.realization.capacitor_values_f[key]
        self._add(Part(f"c{number}{self.stage.index}", CAPACITOR, (node_a, node_b), self.stage.index, key, value, value))

    def res(self, number: int, node_a: str, node_b: str, key: str) -> None:
        network = self.realization.resistor_networks[key]
        name = f"r{number}{self.stage.index}"
        target = network.target_ohms
        if self.exact_values or network.connection == "single":
            value = target if self.exact_values else network.realized_ohms
            self._add(Part(name, RESISTOR, (node_a, node_b), self.stage.index, key, value, target))
            return
        # Series/parallel array (only when explicitly allowed): one part per resistor.
        self.circuit.items.append(f"* {key}: {network.connection} array for target {target:.6f} ohm")
        count = len(network.parts_ohms)
        current_a = node_a
        for position, value in enumerate(network.parts_ohms, start=1):
            if network.connection == "series":
                current_b = node_b if position == count else f"{name}_MID{position}"
                nodes = (current_a, current_b)
                current_a = current_b
            else:
                nodes = (node_a, node_b)
            self._add(Part(f"{name}_{position}", RESISTOR, nodes, self.stage.index, key, value, target))

    def has(self, key: str) -> bool:
        return key in self.realization.resistor_networks or key in self.realization.capacitor_values_f


def _build_stage(inputs: DesignInputs, stage: Stage, total_stages: int, exact_values: bool) -> StageCircuit:
    stage_input, stage_output = stage_ports(stage, total_stages)
    realization = stage.realization
    topology = realization.topology if realization is not None else inputs.topology
    circuit = StageCircuit(stage, topology, stage_input, stage_output)
    circuit.items.extend([f"* Stage input: {stage_input}", f"* Stage output: {stage_output}"])
    if realization is None:
        circuit.items.append("* Missing realization")
        return circuit
    circuit.items.extend(f"* {note}" for note in realization.notes)

    builder = _StageBuilder(inputs, stage, circuit, exact_values)
    if stage.order == 1:
        if topology in {Topology.MFB, Topology.TOW_THOMAS}:
            _first_order_inverting(builder, inputs.kind, stage_input, stage_output)
        else:
            _first_order_follower(builder, inputs.kind, stage_input, stage_output)
    elif topology is Topology.SALLEN_KEY:
        _sallen_key(builder, inputs.kind, stage_input, stage_output)
    elif topology is Topology.MFB:
        _mfb(builder, inputs.kind, stage_input, stage_output)
    elif topology is Topology.TOW_THOMAS:
        _tow_thomas(builder, inputs.kind, stage_input, stage_output)
    elif topology is Topology.ANTONIOU:
        _antoniou(builder, inputs.kind, stage_input, stage_output)
    else:
        circuit.items.append("* Unknown topology")
    return circuit


def _first_order_follower(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2 = w.node(2)
    w.opamp(1, n2, out_node, out_node)
    if kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.res(1, n2, "VREF", "R1")
    else:
        w.res(1, in_node, n2, "R1")
        w.cap(1, n2, "VREF", "C1")


def _first_order_inverting(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
    n2, n3 = w.node(2), w.node(3)
    w.opamp(1, "VREF", n3, out_node)
    if kind is FilterKind.HIGHPASS:
        w.cap(1, in_node, n2, "C1")
        w.res(1, n2, n3, "R1")
    else:
        w.res(1, in_node, n3, "R1")
        w.cap(1, n3, out_node, "C1")
    w.res(2, n3, out_node, "R2")


def _sallen_key(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
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


def _mfb(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
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


def _tow_thomas(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
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


def _antoniou(w: _StageBuilder, kind: FilterKind, in_node: str, out_node: str) -> None:
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
