"""The filter as a real board: stage parts plus supply, virtual ground, input/output coupling and
connectors, with reference designators, op amp packages and footprints.

The schematic, the bill of materials and the PCB are generated from this. Nets keep the netlist
names (``IN``, ``OUT``, ``VREF``, ``E<k>`` between stages) plus ``VCC``, ``GND`` and a few board nets.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from .circuit import CAPACITOR, OPAMP, RESISTOR, Part, StageCircuit, build_circuit
from .models import DesignInputs, DesignResult, OpAmpModel, ResistorSeries
from .netlist import ac_sweep_limits, supply_voltage_for

E6 = (1.0, 1.5, 2.2, 3.3, 4.7, 6.8)


class Mounting(StrEnum):
    SMD = "smd"
    THT = "tht"


@dataclass(slots=True)
class BoardOptions:
    mounting: Mounting = Mounting.SMD


@dataclass(slots=True)
class OpAmpPackage:
    """Pin numbers of one op amp package: sections as (non-inverting, inverting, output)."""

    name: str
    pins: int
    sections: tuple[tuple[str, str, str], ...]
    vplus: str
    vminus: str
    unused: tuple[str, ...] = ()


SINGLE = OpAmpPackage("single", 8, (("3", "2", "6"),), vplus="7", vminus="4", unused=("1", "5", "8"))
DUAL = OpAmpPackage("dual", 8, (("3", "2", "1"), ("5", "6", "7")), vplus="8", vminus="4")
QUAD = OpAmpPackage("quad", 14, (("3", "2", "1"), ("5", "6", "7"), ("10", "9", "8"), ("12", "13", "14")), vplus="4", vminus="11")
PACKAGES = {OpAmpModel.TL082: DUAL, OpAmpModel.LM324: QUAD}
PACKAGE_WORDS = {"single": "", "dual": " (doble)", "quad": " (cuádruple)"}

TOLERANCE = {ResistorSeries.E96: "1 %", ResistorSeries.E48: "2 %", ResistorSeries.E24: "5 %", ResistorSeries.E12: "10 %"}

FOOTPRINTS = {
    Mounting.SMD: {
        "R": "Resistor_SMD:R_0805_2012Metric",
        "C_small": "Capacitor_SMD:C_0805_2012Metric",
        "C_medium": "Capacitor_SMD:C_1206_3216Metric",
        "C_large": "Capacitor_SMD:C_1812_4532Metric",
        "C_decoupling": "Capacitor_SMD:C_0805_2012Metric",
        "C_bulk": "Capacitor_SMD:C_1206_3216Metric",
        "CP": "Capacitor_SMD:CP_Elec_6.3x5.4",
        "U8": "Package_SO:SOIC-8_3.9x4.9mm_P1.27mm",
        "U14": "Package_SO:SOIC-14_3.9x8.7mm_P1.27mm",
    },
    Mounting.THT: {
        "R": "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
        "C_small": "Capacitor_THT:C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2",
        "C_medium": "Capacitor_THT:C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2",
        "C_large": "Capacitor_THT:C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2",
        "C_decoupling": "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
        "C_bulk": "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        "CP": "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
        "U8": "Package_DIP:DIP-8_W7.62mm",
        "U14": "Package_DIP:DIP-14_W7.62mm",
    },
}
CONNECTOR_FOOTPRINT = "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical"
MOUNTING_HOLE_FOOTPRINT = "MountingHole:MountingHole_3.2mm_M3"


def capacitor_label(farads: float) -> str:
    """27e-9 -> '27n', 1e-5 -> '10u', 5.6e-9 -> '5.6n'."""
    for scale, prefix in ((1e-6, "u"), (1e-9, "n"), (1e-12, "p")):
        if farads >= scale * 0.9995:
            return f"{farads / scale:.3g}{prefix}"
    return f"{farads:.3g}"


def resistor_label(ohms: float) -> str:
    for scale, prefix in ((1e6, "M"), (1e3, "k")):
        if ohms >= scale * 0.9995:
            return f"{ohms / scale:.3g}{prefix}"
    return f"{ohms:.3g}"


@dataclass(slots=True)
class Component:
    """One physical part. ``pins`` maps pad number to net name."""

    ref: str
    symbol: str  # R, C, CP, OPAMP, CONN, HOLE
    value: str
    footprint: str
    pins: dict[str, str]
    description: str
    stage: int = 0
    function: str = ""
    package: OpAmpPackage | None = None
    in_bom: bool = True


@dataclass(slots=True)
class OpAmpUnit:
    """One op amp section placed in the schematic."""

    component: Component
    unit: int  # 1-based section number; the power unit is len(sections) + 1
    part: Part | None = None  # stage part it realizes; None for the virtual-ground buffer or a spare
    purpose: str = "stage"  # stage, vref, spare

    @property
    def label(self) -> str:
        return f"{self.component.ref}{chr(ord('A') + self.unit - 1)}"


@dataclass(slots=True)
class Board:
    inputs: DesignInputs
    result: DesignResult
    options: BoardOptions
    stages: list[StageCircuit]
    components: list[Component] = field(default_factory=list)
    units: list[OpAmpUnit] = field(default_factory=list)
    # Stage part name (r31, Xao12...) -> component reference / op amp unit.
    by_part: dict[str, Component] = field(default_factory=dict)
    unit_of: dict[str, OpAmpUnit] = field(default_factory=dict)
    supply_v: float = 15.0
    coupling_f: float = 10e-6

    def component(self, ref: str) -> Component:
        return next(component for component in self.components if component.ref == ref)

    def nets(self) -> dict[str, list[tuple[str, str]]]:
        """Net name -> [(reference, pad)], over every component."""
        nets: dict[str, list[tuple[str, str]]] = {}
        for component in self.components:
            for pad, net in component.pins.items():
                if net:
                    nets.setdefault(net, []).append((component.ref, pad))
        return nets


def net_name(node: str) -> str:
    """Netlist node -> board net: ``0`` is GND and ``1<k>`` (between stages) is ``E<k>``."""
    if node == "0":
        return "GND"
    if node.startswith("1") and node[1:].isdigit():
        return f"E{node[1:]}"
    if node[:1].isdigit():
        return f"N{node}"
    return node


def _next_e6(value: float) -> float:
    exponent = math.floor(math.log10(value))
    for _ in range(3):
        for base in E6:
            candidate = base * 10**exponent
            if candidate >= value * 0.999:
                return candidate
        exponent += 1
    return E6[0] * 10**exponent


def build_board(inputs: DesignInputs, result: DesignResult, options: BoardOptions | None = None) -> Board:
    options = options or BoardOptions()
    stages = build_circuit(inputs, result)
    if any("_" in part.name for stage in stages for part in stage.parts if part.kind == RESISTOR):
        raise ValueError("El esquemático y la PCB usan un solo resistor por posición (sin arreglos serie/paralelo).")
    board = Board(inputs, result, options, stages, supply_v=supply_voltage_for(inputs))
    footprints = FOOTPRINTS[options.mounting]
    smd = options.mounting is Mounting.SMD

    def capacitor_footprint(farads: float) -> str:
        if farads <= 22e-9:
            return footprints["C_small"]
        if farads <= 100e-9:
            return footprints["C_medium"]
        return footprints["C_large"]

    filter_cap_text = "Capacitor cerámico C0G/NP0 5 %" if smd else "Capacitor de película 5 %"
    resistor_text = f"Resistencia {TOLERANCE[inputs.resistor_series]} película metálica" + (" 0805" if smd else " 1/4 W")

    # Stage resistors and capacitors: R<stage><nn>, C<stage><nn>.
    for stage in stages:
        counters = {RESISTOR: 0, CAPACITOR: 0}
        for part in stage.parts:
            if part.kind == OPAMP:
                continue
            counters[part.kind] += 1
            ref = f"{part.kind}{stage.stage.index}{counters[part.kind]:02d}"
            pins = {"1": net_name(part.nodes[0]), "2": net_name(part.nodes[1])}
            if part.kind == RESISTOR:
                component = Component(ref, "R", resistor_label(part.value), footprints["R"], pins, resistor_text, stage.stage.index, part.key)
            else:
                component = Component(
                    ref, "C", capacitor_label(part.value), capacitor_footprint(part.value), pins, filter_cap_text, stage.stage.index, part.key
                )
            board.components.append(component)
            board.by_part[part.name] = component

    _assign_opamps(board, footprints)
    _add_board_extras(board, footprints, smd, resistor_text)
    return board


def _assign_opamps(board: Board, footprints: dict[str, str]) -> None:
    model = board.inputs.opamp
    package = PACKAGES.get(model, SINGLE)
    footprint = footprints["U14" if package.pins == 14 else "U8"]
    stage_sections = [part for stage in board.stages for part in stage.parts if part.kind == OPAMP]
    total = len(stage_sections) + 1  # plus the virtual-ground buffer
    per_package = len(package.sections)
    count = math.ceil(total / per_package)
    packages: list[Component] = []
    for number in range(1, count + 1):
        pins = {package.vplus: "VCC", package.vminus: "GND"}
        description = f"Amplificador operacional {model.value}{PACKAGE_WORDS[package.name]}"
        component = Component(f"U{number}", "OPAMP", model.value, footprint, pins, description, package=package)
        packages.append(component)
        board.components.append(component)

    slots = [(component, unit) for component in packages for unit in range(1, per_package + 1)]
    for (component, unit), part in zip(slots, stage_sections):
        plus, minus, out = component.package.sections[unit - 1]
        component.pins.update({plus: net_name(part.nodes[0]), minus: net_name(part.nodes[1]), out: net_name(part.nodes[2])})
        component.stage = component.stage or part.stage
        op_unit = OpAmpUnit(component, unit, part)
        board.units.append(op_unit)
        board.unit_of[part.name] = op_unit
        board.by_part[part.name] = component

    leftover = slots[len(stage_sections) :]
    (component, unit), spares = leftover[0], leftover[1:]
    plus, minus, out = component.package.sections[unit - 1]
    component.pins.update({plus: "VDIV", minus: "VREF", out: "VREF"})
    board.units.append(OpAmpUnit(component, unit, purpose="vref"))
    for component, unit in spares:
        # Unused section: follower at the virtual ground, so it neither oscillates nor saturates.
        plus, minus, out = component.package.sections[unit - 1]
        spare_net = f"SPARE_{component.ref}{chr(ord('A') + unit - 1)}"
        component.pins.update({plus: "VREF", minus: spare_net, out: spare_net})
        board.units.append(OpAmpUnit(component, unit, purpose="spare"))
    for component in packages:
        for pad in component.package.unused:
            component.pins.setdefault(pad, "")


def _first_stage_input_impedance(board: Board, frequency: float) -> float:
    """Smallest impedance hanging from IN at ``frequency`` (sets the input coupling capacitor)."""
    impedances = []
    for stage in board.stages[:1]:
        for part in stage.parts:
            if part.kind == OPAMP or "IN" not in part.nodes:
                continue
            if part.kind == RESISTOR:
                impedances.append(part.value)
            else:
                impedances.append(1 / (2 * math.pi * frequency * part.value))
    return min(impedances) if impedances else 10e3


def _add_board_extras(board: Board, footprints: dict[str, str], smd: bool, resistor_text: str) -> None:
    supply = board.supply_v
    voltage = 25 if supply <= 15 else 50
    bulk_text = f"Capacitor cerámico X7R {voltage} V" if smd else f"Capacitor electrolítico {voltage} V"
    decoupling_text = "Capacitor cerámico X7R" if smd else "Capacitor cerámico de disco"
    bulk_symbol = "C" if smd else "CP"

    # Coupling: corner a decade below the lowest plotted frequency, with the first stage's input impedance.
    f_low = ac_sweep_limits(board.inputs)[0] / 10
    coupling = _next_e6(max(1e-6, 1 / (2 * math.pi * _first_stage_input_impedance(board, f_low) * f_low)))
    board.coupling_f = coupling

    def add(ref, symbol, value, footprint, pins, description, function, in_bom=True):
        board.components.append(Component(ref, symbol, value, footprint, pins, description, 0, function, in_bom=in_bom))

    add("J1", "CONN", "Alimentación", CONNECTOR_FOOTPRINT, {"1": "VCC", "2": "GND"}, "Conector de 2 pines 2.54 mm", "Alimentación")
    add("J2", "CONN", "Entrada", CONNECTOR_FOOTPRINT, {"1": "SIG_IN", "2": "GND"}, "Conector de 2 pines 2.54 mm", "Entrada")
    add("J3", "CONN", "Salida", CONNECTOR_FOOTPRINT, {"1": "SIG_OUT", "2": "GND"}, "Conector de 2 pines 2.54 mm", "Salida")
    # Polarized parts list the positive pad first.
    add("C1", bulk_symbol, "10u", footprints["C_bulk"], {"1": "VCC", "2": "GND"}, bulk_text, "Desacoplo de la fuente")
    add("R1", "R", "10k", footprints["R"], {"1": "VCC", "2": "VDIV"}, resistor_text, "Divisor de tierra virtual")
    add("R2", "R", "10k", footprints["R"], {"1": "VDIV", "2": "GND"}, resistor_text, "Divisor de tierra virtual")
    add("C2", bulk_symbol, "10u", footprints["C_bulk"], {"1": "VDIV", "2": "GND"}, bulk_text, "Filtro de tierra virtual")
    # Up to 22 uF the coupling capacitors are like the bulk ones; bigger ones are electrolytic.
    if coupling > 22e-6:
        coupling_symbol, coupling_footprint, coupling_text = "CP", footprints["CP"], f"Capacitor electrolítico {voltage} V"
    else:
        coupling_symbol, coupling_footprint, coupling_text = bulk_symbol, footprints["C_bulk"], bulk_text
    add("C3", coupling_symbol, capacitor_label(coupling), coupling_footprint, {"1": "IN", "2": "SIG_IN"}, coupling_text, "Acoplamiento de entrada")
    add("R3", "R", "100k", footprints["R"], {"1": "IN", "2": "VREF"}, resistor_text, "Polarización de entrada")
    add("C4", coupling_symbol, capacitor_label(coupling), coupling_footprint, {"1": "OUT", "2": "SIG_OUT"}, coupling_text, "Acoplamiento de salida")
    add("R4", "R", "100k", footprints["R"], {"1": "SIG_OUT", "2": "GND"}, resistor_text, "Descarga de salida")
    packages = [component for component in board.components if component.symbol == "OPAMP"]
    for number, package in enumerate(packages, start=5):
        add(f"C{number}", "C", "100n", footprints["C_decoupling"], {"1": "VCC", "2": "GND"}, decoupling_text, f"Desacoplo de {package.ref}")
    for number in range(1, 5):
        add(f"H{number}", "HOLE", "M3", MOUNTING_HOLE_FOOTPRINT, {}, "Barreno de montaje M3", "Montaje", in_bom=False)


def bom_rows(board: Board) -> list[dict[str, str]]:
    """Grouped bill of materials: one row per value, footprint and description."""
    groups: dict[tuple[str, str, str], list[str]] = {}
    for component in board.components:
        if not component.in_bom:
            continue
        groups.setdefault((component.value, component.footprint, component.description), []).append(component.ref)

    def order(ref: str) -> tuple[str, int]:
        letters = ref.rstrip("0123456789")
        return letters, int(ref[len(letters) :])

    rows = []
    for (value, footprint, description), refs in groups.items():
        refs.sort(key=order)
        rows.append(
            {
                "Cantidad": str(len(refs)),
                "Referencias": ", ".join(refs),
                "Valor": value,
                "Descripción": description,
                "Huella": footprint.split(":", 1)[1],
            }
        )
    rows.sort(key=lambda row: order(row["Referencias"].split(",")[0]))
    return rows


def bom_csv(board: Board) -> str:
    import csv
    import io

    buffer = io.StringIO()
    rows = bom_rows(board)
    writer = csv.DictWriter(buffer, fieldnames=list(rows[0]), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    # Byte order mark: Excel needs it to read the accents as UTF-8.
    return "﻿" + buffer.getvalue()
