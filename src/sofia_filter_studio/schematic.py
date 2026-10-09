"""Schematic of the board, drawn from one template per topology.

The drawing (symbols, wires, labels) is built once and then rendered as SVG for the apps and as a
KiCad schematic. ``check_connectivity`` rebuilds the nets from the drawing with KiCad's rules and is
used by the tests to prove the drawing matches the circuit.

Coordinates are grid units of 2.54 mm with y pointing down, like the schematic sheet.
"""

from __future__ import annotations

import html
import math
import uuid
from dataclasses import dataclass, field

from . import __version__
from .board import Board, Component, OpAmpUnit, net_name
from .circuit import CAPACITOR, OPAMP, RESISTOR, Part, StageCircuit
from .models import FilterKind, Topology
from .synthesis import KIND_NAMES, TOPOLOGY_NAMES
from .units import format_quantity

GRID = 2.54
Point = tuple[float, float]


# Symbols -----------------------------------------------------------------------------------------
@dataclass(slots=True)
class PinDef:
    number: str
    name: str
    x: float  # library coordinates in mm, y up; (x, y) is the connection point
    y: float
    angle: int  # direction from the connection point towards the body
    length: float
    kind: str = "passive"
    hidden: bool = False


@dataclass(slots=True)
class SymbolDef:
    name: str
    reference: str
    pins: list[PinDef]
    # Graphics in library mm: ("rect", x1, y1, x2, y2, filled) | ("line", [(x, y), ...], width, filled) | ("circle", x, y, r)
    graphics: list[tuple]
    body: tuple[float, float, float, float]  # x1, y1, x2, y2 in library mm (for overlap checks)
    power: bool = False
    show_pin_names: bool = False
    units: int = 1
    unit_pins: dict[int, list[PinDef]] = field(default_factory=dict)  # multi-unit symbols


def _two_pin(name: str, reference: str, graphics: list[tuple], inner: float) -> SymbolDef:
    pins = [PinDef("1", "~", 0, 5.08, 270, 5.08 - inner), PinDef("2", "~", 0, -5.08, 90, 5.08 - inner)]
    return SymbolDef(name, reference, pins, graphics, (-1.2, -inner, 1.2, inner))


RESISTOR_SYMBOL = _two_pin("R", "R", [("rect", -1.016, -2.54, 1.016, 2.54, False)], 2.54)
CAPACITOR_SYMBOL = _two_pin(
    "C", "C", [("line", [(-2.032, 0.762), (2.032, 0.762)], 0.508, False), ("line", [(-2.032, -0.762), (2.032, -0.762)], 0.508, False)], 0.762
)
POLARIZED_SYMBOL = _two_pin(
    "CP",
    "C",
    [
        ("line", [(-2.032, 0.762), (2.032, 0.762)], 0.508, False),
        ("rect", -2.032, -1.016, 2.032, -0.508, True),
        ("line", [(-1.778, 2.032), (-0.762, 2.032)], 0.254, False),
        ("line", [(-1.27, 2.54), (-1.27, 1.524)], 0.254, False),
    ],
    0.762,
)
POLARIZED_SYMBOL.pins[1].length = 5.08 - 0.508
POLARIZED_SYMBOL.body = (-2.1, -1.1, 2.1, 0.9)
RESISTOR_SYMBOL.body = (-1.1, -2.6, 1.1, 2.6)
CAPACITOR_SYMBOL.body = (-2.1, -0.9, 2.1, 0.9)
CONNECTOR_SYMBOL = SymbolDef(
    "CONN2",
    "J",
    [PinDef("1", "Pin_1", 5.08, 0, 180, 2.54), PinDef("2", "Pin_2", 5.08, -2.54, 180, 2.54)],
    [("rect", -1.27, 1.27, 2.54, -3.81, False)],
    (-1.4, -3.9, 2.6, 1.4),
)
HOLE_SYMBOL = SymbolDef("HOLE", "H", [], [("circle", 0, 0, 1.27)], (-1.4, -1.4, 1.4, 1.4))
OPAMP_GRAPHICS = [("line", [(-5.08, 5.08), (5.08, 0), (-5.08, -5.08), (-5.08, 5.08)], 0.254, "background")]
POWER_UNIT_GRAPHICS = [("rect", -2.54, -5.08, 2.54, 5.08, "background")]


def _opamp_symbol(package) -> SymbolDef:
    """One unit per section (with + on top) plus a power unit with V+ and V-."""
    unit_pins: dict[int, list[PinDef]] = {}
    for unit, (plus, minus, out) in enumerate(package.sections, start=1):
        unit_pins[unit] = [
            PinDef(plus, "+", -7.62, 2.54, 0, 2.54, "input"),
            PinDef(minus, "-", -7.62, -2.54, 0, 2.54, "input"),
            PinDef(out, "~", 7.62, 0, 180, 2.54, "output"),
        ]
    power = [PinDef(package.vplus, "V+", 0, 7.62, 270, 2.54, "power_in"), PinDef(package.vminus, "V-", 0, -7.62, 90, 2.54, "power_in")]
    power += [PinDef(pad, "NC", -2.54, 2.54 - 1.27 * index, 0, 0, "no_connect", hidden=True) for index, pad in enumerate(package.unused)]
    unit_pins[len(package.sections) + 1] = power
    return SymbolDef(
        f"OPAMP_{package.name.upper()}",
        "U",
        [],
        OPAMP_GRAPHICS,
        (-5.08, -5.08, 5.08, 5.08),
        show_pin_names=True,
        units=len(package.sections) + 1,
        unit_pins=unit_pins,
    )


def _power_symbol(name: str, net: str, up: bool, graphics: list[tuple], kind: str = "power_in") -> SymbolDef:
    y_sign = 1 if up else -1
    body = (-1.4, 0.2 * y_sign, 1.4, 2.8 * y_sign)
    body = (body[0], min(body[1], body[3]), body[2], max(body[1], body[3]))
    return SymbolDef(name, "#PWR" if kind == "power_in" else "#FLG", [PinDef("1", net, 0, 0, 90 if up else 270, 0, kind, hidden=True)], graphics, body, power=True)


GND_SYMBOL = _power_symbol(
    "GND",
    "GND",
    False,
    [
        ("line", [(0, 0), (0, -1.27)], 0.254, False),
        ("line", [(-1.524, -1.27), (1.524, -1.27)], 0.254, False),
        ("line", [(-1.016, -1.778), (1.016, -1.778)], 0.254, False),
        ("line", [(-0.508, -2.286), (0.508, -2.286)], 0.254, False),
    ],
)
VCC_SYMBOL = _power_symbol(
    "VCC", "VCC", True, [("line", [(0, 0), (0, 1.27)], 0.254, False), ("line", [(-1.27, 1.27), (1.27, 1.27)], 0.254, False), ("line", [(-0.762, 1.27), (0, 2.286), (0.762, 1.27)], 0.254, False)]
)
VREF_DOWN_SYMBOL = _power_symbol(
    "VREF", "VREF", False, [("line", [(0, 0), (0, -1.016)], 0.254, False), ("line", [(-1.27, -1.016), (1.27, -1.016), (0, -2.286), (-1.27, -1.016)], 0.254, False)]
)
VREF_UP_SYMBOL = _power_symbol(
    "VREF_UP", "VREF", True, [("line", [(0, 0), (0, 1.016)], 0.254, False), ("line", [(-1.27, 1.016), (1.27, 1.016), (0, 2.286), (-1.27, 1.016)], 0.254, False)]
)
FLAG_SYMBOL = _power_symbol(
    "PWR_FLAG", "PWR_FLAG", True, [("line", [(0, 0), (0, 1.27), (-1.016, 1.905), (0, 2.54), (1.016, 1.905), (0, 1.27)], 0.254, False)], kind="power_out"
)
POWER_SYMBOLS = {symbol.name: symbol for symbol in (GND_SYMBOL, VCC_SYMBOL, VREF_DOWN_SYMBOL, VREF_UP_SYMBOL, FLAG_SYMBOL)}
TWO_PIN = {"R": RESISTOR_SYMBOL, "C": CAPACITOR_SYMBOL, "CP": POLARIZED_SYMBOL}


def _transform(x: float, y: float, rotation: int, mirror: str | None) -> Point:
    """Library mm (y up) -> sheet offset in grid units (y down), as KiCad places symbols."""
    if mirror == "x":
        y = -y
    elif mirror == "y":
        x = -x
    for _ in range((rotation // 90) % 4):
        x, y = -y, x
    return x / GRID, -y / GRID


# Drawing -----------------------------------------------------------------------------------------
@dataclass(slots=True)
class Placed:
    symbol: SymbolDef
    x: float
    y: float
    rotation: int = 0
    mirror: str | None = None
    unit: int = 1
    ref: str = ""
    value: str = ""
    footprint: str = ""
    component: Component | None = None
    texts: list[tuple[str, float, float, str]] = field(default_factory=list)  # (text, x, y, anchor)

    def pin_defs(self) -> list[PinDef]:
        return self.symbol.unit_pins.get(self.unit, self.symbol.pins) if self.symbol.unit_pins else self.symbol.pins

    def pins(self) -> dict[str, Point]:
        result = {}
        for pin in self.pin_defs():
            dx, dy = _transform(pin.x, pin.y, self.rotation, self.mirror)
            result[pin.number] = (self.x + dx, self.y + dy)
        return result

    def body(self) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = self.symbol.body
        corners = [_transform(px, py, self.rotation, self.mirror) for px, py in ((x1, y1), (x2, y2))]
        xs = [self.x + cx for cx, _ in corners]
        ys = [self.y + cy for _, cy in corners]
        return min(xs), min(ys), max(xs), max(ys)


@dataclass(slots=True)
class Label:
    name: str
    x: float
    y: float
    angle: int = 0  # 0: text to the right of the anchor, 180: to the left


@dataclass(slots=True)
class Drawing:
    symbols: list[Placed] = field(default_factory=list)
    wires: list[tuple[Point, Point]] = field(default_factory=list)
    labels: list[Label] = field(default_factory=list)
    texts: list[tuple[str, float, float, float]] = field(default_factory=list)  # (text, x, y, size mm)

    def offset(self, dx: float, dy: float) -> "Drawing":
        moved = Drawing()
        for placed in self.symbols:
            moved.symbols.append(
                Placed(
                    placed.symbol, placed.x + dx, placed.y + dy, placed.rotation, placed.mirror, placed.unit, placed.ref, placed.value,
                    placed.footprint, placed.component, [(text, x + dx, y + dy, anchor) for text, x, y, anchor in placed.texts],
                )
            )
        moved.wires = [((a[0] + dx, a[1] + dy), (b[0] + dx, b[1] + dy)) for a, b in self.wires]
        moved.labels = [Label(label.name, label.x + dx, label.y + dy, label.angle) for label in self.labels]
        moved.texts = [(text, x + dx, y + dy, size) for text, x, y, size in self.texts]
        return moved

    def extend(self, other: "Drawing") -> None:
        self.symbols += other.symbols
        self.wires += other.wires
        self.labels += other.labels
        self.texts += other.texts

    def bounds(self) -> tuple[float, float, float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for placed in self.symbols:
            x1, y1, x2, y2 = placed.body()
            xs += [x1, x2]
            ys += [y1, y2]
            for point in placed.pins().values():
                xs.append(point[0])
                ys.append(point[1])
            for text, x, y, anchor in placed.texts:
                width = len(text) * 0.55
                xs += [x, x + width if anchor == "start" else x - width if anchor == "end" else x + width / 2]
                ys += [y - 0.6, y + 0.6]
        for a, b in self.wires:
            xs += [a[0], b[0]]
            ys += [a[1], b[1]]
        for label in self.labels:
            width = len(label.name) * 0.55 + 0.5
            xs += [label.x, label.x + width if label.angle == 0 else label.x - width]
            ys += [label.y - 0.8, label.y]
        for text, x, y, size in self.texts:
            xs += [x, x + len(text) * size / GRID * 0.6]
            ys += [y - size / GRID, y]
        return min(xs), min(ys), max(xs), max(ys)


class _Block(Drawing):
    """Drawing helpers for one stage or one board section."""

    def __init__(self, board: Board, stage: StageCircuit | None = None) -> None:
        super().__init__()
        self.board = board
        self.stage = stage
        self.pool: dict[frozenset, list[Part]] = {}
        self.amps: dict[int, Part] = {}
        if stage is not None:
            suffix = len(str(stage.stage.index))
            for part in stage.parts:
                if part.kind == OPAMP:
                    self.amps[int(part.name[3:-suffix])] = part
                else:
                    self.pool.setdefault(frozenset(part.role), []).append(part)

    # Parts of the stage, by the roles of their nodes.
    def take(self, a: str, b: str, kind: str | None = None) -> Part | None:
        parts = self.pool.get(frozenset((a, b)), [])
        for index, part in enumerate(parts):
            if kind is None or part.kind == kind:
                return parts.pop(index)
        return None

    def leftovers(self) -> list[Part]:
        return [part for parts in self.pool.values() for part in parts]

    def wire(self, *points: Point) -> None:
        for a, b in zip(points, points[1:]):
            if a != b:
                self.wires.append((a, b))

    def two(self, part: Part | Component | None, x: float, y: float, vertical: bool, side: str = "right") -> tuple[Point, Point]:
        """Resistor or capacitor centered at (x, y); returns its ends (left, right) or (top, bottom).

        Horizontal parts carry reference and value on one line above; vertical ones beside them, on
        ``side``.
        """
        ends = ((x, y - 2), (x, y + 2)) if vertical else ((x - 2, y), (x + 2, y))
        if part is None:
            return ends
        component = part if isinstance(part, Component) else self.board.by_part[part.name]
        symbol = TWO_PIN[component.symbol]
        if component.symbol == "CP":
            raise ValueError("los capacitores polarizados se colocan con polar()")
        placed = Placed(symbol, x, y, 0 if vertical else 90, None, 1, component.ref, component.value, component.footprint, component)
        if vertical:
            dx, anchor = (1.1, "start") if side == "right" else (-1.1, "end")
            placed.texts = [(component.ref, x + dx, y - 0.25, anchor), (component.value, x + dx, y + 0.85, anchor)]
        else:
            placed.texts = [(component.ref, x - 0.2, y - 0.9, "end"), (component.value, x + 0.2, y - 0.9, "start")]
        self.symbols.append(placed)
        return ends

    def polar(self, component: Component, x: float, y: float, positive_top: bool) -> tuple[Point, Point]:
        """Vertical capacitor (polarized or not); returns (top, bottom)."""
        symbol = TWO_PIN[component.symbol]
        rotation = 0 if positive_top or component.symbol != "CP" else 180
        placed = Placed(symbol, x, y, rotation, None, 1, component.ref, component.value, component.footprint, component)
        placed.texts = [(component.ref, x + 1.1, y - 0.25, "start"), (component.value, x + 1.1, y + 0.85, "start")]
        self.symbols.append(placed)
        return (x, y - 2), (x, y + 2)

    def amp(self, unit: OpAmpUnit, x: float, y: float, minus_top: bool = True, flip: bool = False, text: str = "below") -> dict[str, Point]:
        """Op amp section; returns the points of '+', '-' and 'out'."""
        component = unit.component
        mirror = "y" if flip else ("x" if minus_top else None)
        placed = Placed(_symbol_for(component), x, y, 0, mirror, unit.unit, component.ref, component.value, component.footprint, component)
        tx = x - 1 if flip else x + 1
        rows = (y + 2.9, y + 3.9) if text == "below" else (y - 3.3, y - 2.3)
        placed.texts = [(unit.label, tx, rows[0], "middle"), (component.value, tx, rows[1], "middle")]
        self.symbols.append(placed)
        if flip:
            return {"+": (x + 3, y - 1), "-": (x + 3, y + 1), "out": (x - 3, y)}
        if minus_top:
            return {"-": (x - 3, y - 1), "+": (x - 3, y + 1), "out": (x + 3, y)}
        return {"+": (x - 3, y - 1), "-": (x - 3, y + 1), "out": (x + 3, y)}

    def stage_amp(self, number: int) -> OpAmpUnit:
        return self.board.unit_of[self.amps[number].name]

    def power(self, name: str, point: Point, rotation: int = 0) -> None:
        symbol = POWER_SYMBOLS[name]
        placed = Placed(symbol, point[0], point[1], rotation, ref="#", value=symbol.pins[0].name)
        if name not in ("PWR_FLAG", "GND"):
            offset = -2.3 if symbol.pins[0].angle == 90 else 2.6
            placed.texts = [(symbol.pins[0].name, point[0], point[1] + offset, "middle")]
        self.symbols.append(placed)

    def vref(self, point: Point, up: bool = False) -> None:
        self.power("VREF_UP" if up else "VREF", point)

    def port(self, role: str, point: Point, angle: int = 0) -> None:
        """Net label of the stage input or output, at the end of a short stub."""
        name = net_name(self.stage.input if role == "in" else self.stage.output)
        step = 1 if angle == 0 else -1
        end = (point[0] + step, point[1])
        self.wire(point, end)
        self.labels.append(Label(name, end[0], end[1], angle))

    def port_down(self, role: str, point: Point) -> None:
        name = net_name(self.stage.input if role == "in" else self.stage.output)
        end = (point[0], point[1] + 1)
        self.wire(point, end)
        self.labels.append(Label(name, end[0], end[1], 0))

    def to(self, far: str, point: Point, vertical_down: bool = True) -> None:
        """Connect the far end of an element to VREF or to the stage input."""
        if far == "vref":
            self.vref(point)
        elif vertical_down:
            self.port_down(far, point)
        else:
            self.port(far, point, 180)


_OPAMP_SYMBOLS: dict[str, SymbolDef] = {}


def _symbol_for(component: Component) -> SymbolDef:
    package = component.package
    if package.name not in _OPAMP_SYMBOLS:
        _OPAMP_SYMBOLS[package.name] = _opamp_symbol(package)
    return _OPAMP_SYMBOLS[package.name]


# Stage templates ---------------------------------------------------------------------------------
def _first_order_follower(b: _Block) -> None:
    pins = b.amp(b.stage_amp(1), 9, 4)
    b.port("in", (0, 5), 180)
    left, right = b.two(b.take("in", "n2"), 3, 5, vertical=False)
    b.wire((0, 5), left)
    b.wire(right, pins["+"])
    top, bottom = b.two(b.take("n2", "vref"), 5, 8, vertical=True)
    b.wire(right, top)
    b.vref(bottom)
    b.wire(pins["-"], (6, 2), (13, 2), (13, 4))
    b.wire(pins["out"], (14, 4))
    b.port("out", (14, 4))


def _first_order_inverting(b: _Block) -> None:
    pins = b.amp(b.stage_amp(1), 14, 5)
    b.port("in", (0, 4), 180)
    b.wire((0, 4), (1, 4))
    first = b.take("in", "n2")
    if first is not None:
        b.two(first, 3, 4, vertical=False)
        b.two(b.take("n2", "n3"), 7, 4, vertical=False)
    else:
        b.wire((1, 4), (5, 4))
        b.two(b.take("in", "n3"), 7, 4, vertical=False)
    b.wire((9, 4), pins["-"])
    b.vref(pins["+"])
    feedback = [b.take("n3", "out", RESISTOR), b.take("n3", "out", CAPACITOR)]
    rows = [part for part in feedback if part is not None]
    previous = (10, 4)
    for row, part in zip((1, -2), rows):
        b.wire(previous, (10, row), (12, row))
        b.two(part, 14, row, vertical=False)
        b.wire((16, row), (18, row), (18, 5) if row == 1 else (18, 1))
        previous = (10, row)
    b.wire(pins["out"], (19, 5))
    b.port("out", (19, 5))


def _sallen_key(b: _Block) -> None:
    pins = b.amp(b.stage_amp(1), 19, 9)
    b.port("in", (0, 10), 180)
    b.wire((0, 10), (1, 10))
    b.two(b.take("in", "n2"), 3, 10, vertical=False)
    b.wire((5, 10), (9, 10))
    b.two(b.take("n2", "n3"), 11, 10, vertical=False)
    b.wire((13, 10), pins["+"])
    top, bottom = b.two(b.take("n3", "vref"), 14, 13, vertical=True)
    b.wire((14, 10), top)
    b.vref(bottom)
    for x, side in ((6, "left"), (8, "right")):
        shunt = b.take("n2", "vref")
        if shunt is not None:
            top, bottom = b.two(shunt, x, 13, vertical=True, side=side)
            b.wire((x, 10), top)
            b.vref(bottom)
    top, bottom = b.two(b.take("n2", "out"), 7, 7, vertical=True)
    b.wire(bottom, (7, 10))
    b.wire(top, (7, 2), (25, 2), (25, 9))
    b.wire(pins["out"], (26, 9))
    b.port("out", (26, 9))
    feedback = b.take("n4", "out")
    if feedback is None:
        b.wire(pins["-"], (16, 6), (24, 6), (24, 9))
        return
    b.wire(pins["-"], (16, 6))
    b.two(feedback, 20, 6, vertical=False)
    b.wire((16, 6), (18, 6))
    b.wire((22, 6), (24, 6), (24, 9))
    left, right = b.two(b.take("n4", "vref"), 13, 6, vertical=False)
    b.wire(right, (16, 6))
    b.vref(left, up=True)


def _mfb(b: _Block) -> None:
    pins = b.amp(b.stage_amp(1), 17, 9)
    b.port("in", (0, 8), 180)
    b.wire((0, 8), (1, 8))
    b.two(b.take("in", "n2"), 3, 8, vertical=False)
    b.wire((5, 8), (8, 8))
    b.two(b.take("n2", "n3"), 10, 8, vertical=False)
    b.wire((12, 8), pins["-"])
    shunt = b.take("n2", "vref")
    if shunt is not None:
        top, bottom = b.two(shunt, 6, 11, vertical=True)
        b.wire((6, 8), top)
        b.vref(bottom)
    b.wire((13, 8), (13, 5), (15, 5))
    b.two(b.take("n3", "out"), 17, 5, vertical=False)
    b.wire((19, 5), (22, 5), (22, 9))
    b.wire((7, 8), (7, 2), (12, 2))
    b.two(b.take("n2", "out"), 14, 2, vertical=False)
    b.wire((16, 2), (23, 2), (23, 9))
    b.vref(pins["+"])
    b.wire(pins["out"], (24, 9))
    b.port("out", (24, 9))


def _tow_thomas(b: _Block, kind: FilterKind) -> None:
    bp, lp = ("n3", "out") if kind is FilterKind.LOWPASS else ("out", "n5")
    b.port("in", (0, 7), 180)
    b.wire((0, 7), (2, 7))
    r1 = b.take("in", "n2", RESISTOR)
    cff = b.take("in", "n2", CAPACITOR)
    rff = b.take("in", "n4")
    top = -2 if rff else (4 if cff else 7)
    b.wire((2, 7), (2, top))
    if r1:
        b.two(r1, 4, 7, vertical=False)
    if cff:
        b.two(cff, 4, 4, vertical=False)
        b.wire((6, 4), (6, 7))
    a1 = b.amp(b.stage_amp(1), 14, 8)
    b.wire((6, 7), a1["-"])
    b.vref(a1["+"])
    b.wire((8, 7), (8, 4), (11, 4))
    b.two(b.take("n2", bp, CAPACITOR), 13, 4, vertical=False)
    b.wire((15, 4), (18, 4), (18, 8))
    b.wire((8, 4), (8, 1), (11, 1))
    b.two(b.take("n2", bp, RESISTOR), 13, 1, vertical=False)
    b.wire((15, 1), (18, 1), (18, 4))
    b.wire(a1["out"], (19, 8))
    b.two(b.take(bp, "n4"), 21, 8, vertical=False)
    a2 = b.amp(b.stage_amp(2), 28, 9)
    b.wire((23, 8), a2["-"])
    b.vref(a2["+"])
    b.wire((24, 8), (24, 5), (26, 5))
    b.two(b.take("n4", lp), 28, 5, vertical=False)
    b.wire((30, 5), (33, 5), (33, 9))
    if rff:
        b.wire((2, -2), (19, -2))
        b.two(rff, 21, -2, vertical=False)
        b.wire((23, -2), (24, -2), (24, 5))
    b.wire(a2["out"], (35, 9))
    b.two(b.take(lp, "n6"), 37, 9, vertical=False)
    a3 = b.amp(b.stage_amp(3), 44, 10)
    b.wire((39, 9), a3["-"])
    b.vref(a3["+"])
    b.wire((40, 9), (40, 6), (42, 6))
    b.two(b.take("n6", "n7"), 44, 6, vertical=False)
    b.wire((46, 6), (48, 6), (48, 10))
    b.wire(a3["out"], (49, 10), (49, 15), (32, 15))
    b.two(b.take("n7", "n2"), 30, 15, vertical=False)
    b.wire((28, 15), (9, 15), (9, 7))
    if lp == "out":
        b.wire((34, 9), (34, 11))
        b.labels.append(Label(net_name(b.stage.output), 34, 11, 0))
    else:
        b.wire((19, 8), (19, 11))
        b.labels.append(Label(net_name(b.stage.output), 19, 11, 0))


def _antoniou(b: _Block) -> None:
    # Impedance ladder X(n6) - n5 - n4 - n3 - n2 - ground/input, one op amp on each side.
    b.two(b.take("n5", "n6"), 14, 4, vertical=True)
    b.two(b.take("n4", "n5"), 14, 8, vertical=True)
    b.two(b.take("n3", "n4"), 14, 12, vertical=True, side="left")
    b.two(b.take("n2", "n3"), 14, 16, vertical=True, side="left")
    bottom = b.take("n2", "vref")
    bottom_far = "vref"
    if bottom is None:
        bottom, bottom_far = b.take("n2", "in"), "in"
    _, end = b.two(bottom, 14, 20, vertical=True)
    b.to(bottom_far, end)
    extra = b.take("n2", "in")
    if extra is not None:
        left, right = b.two(extra, 10, 18, vertical=False)
        b.wire(right, (14, 18))
        b.port("in", left, 180)
    a1 = b.amp(b.stage_amp(1), 21, 14)
    b.wire((14, 10), (17, 10), (17, 13), a1["-"])
    b.wire((14, 18), (17, 18), (17, 15), a1["+"])
    b.wire(a1["out"], (25, 14), (25, 6), (14, 6))
    a2 = b.amp(b.stage_amp(2), 8, 7, flip=True)
    b.wire((14, 2), (12, 2), (12, 6), a2["+"])
    b.wire((14, 10), (13, 10), (13, 8), a2["-"])
    b.wire(a2["out"], (4, 7), (4, 14), (14, 14))
    a3 = b.amp(b.stage_amp(3), 44, 3, minus_top=False, text="above")
    b.wire((14, 2), a3["+"])
    hub = [(b.take("n6", far, kind), far) for far in ("vref", "in") for kind in (CAPACITOR, RESISTOR)]
    for x, (part, far) in zip((27, 31, 35, 39), [(part, far) for part, far in hub if part is not None]):
        _, end = b.two(part, x, 4, vertical=True)
        b.to(far, end)
    gain = b.take("n7", "out")
    if gain is None:
        b.wire(a3["-"], (41, 6), (48, 6), (48, 3))
    else:
        b.wire(a3["-"], (41, 6), (42, 6))
        b.two(gain, 44, 6, vertical=False)
        b.wire((46, 6), (48, 6), (48, 3))
        b.wire((41, 6), (41, 7))
        _, end = b.two(b.take("n7", "vref"), 41, 9, vertical=True)
        b.vref(end)
    b.wire(a3["out"], (49, 3))
    b.port("out", (49, 3))


def _draw_stage(board: Board, stage: StageCircuit) -> Drawing:
    block = _Block(board, stage)
    kind = board.inputs.kind
    if stage.stage.order == 1:
        if stage.topology in {Topology.MFB, Topology.TOW_THOMAS}:
            _first_order_inverting(block)
        else:
            _first_order_follower(block)
    elif stage.topology is Topology.SALLEN_KEY:
        _sallen_key(block)
    elif stage.topology is Topology.MFB:
        _mfb(block)
    elif stage.topology is Topology.TOW_THOMAS:
        _tow_thomas(block, kind)
    elif stage.topology is Topology.ANTONIOU:
        _antoniou(block)
    left = block.leftovers()
    if left:
        raise ValueError(f"La plantilla de {stage.topology.value} no dibujó {[part.key for part in left]} (etapa {stage.stage.index})")
    return block


# Board section -----------------------------------------------------------------------------------
def _draw_power(board: Board) -> Drawing:
    b = _Block(board)
    b.texts.append(("Alimentación", 0, -1, 1.8))
    j1 = board.component("J1")
    b.symbols.append(Placed(CONNECTOR_SYMBOL, 0, 2, ref=j1.ref, value=j1.value, footprint=j1.footprint, component=j1,
                            texts=[(j1.ref, 0.4, 0.2, "middle"), (j1.value, 0.4, 4.6, "middle")]))
    b.power("PWR_FLAG", (4, 2))
    b.power("VCC", (6, 2))
    b.wire((2, 3), (5, 3))
    b.power("PWR_FLAG", (3, 3), rotation=180)
    b.power("GND", (5, 3))
    packages = [component for component in board.components if component.symbol == "OPAMP"]
    decoupling = [board.component(f"C{number}") for number in range(5, 5 + len(packages))]
    caps = [board.component("C1")] + decoupling
    last_x = 9
    for index, cap in enumerate(caps):
        x = 9 + 4 * index
        top, bottom = b.polar(cap, x, 4, positive_top=True)
        b.power("GND", bottom)
        last_x = x
    b.wire((2, 2), (last_x, 2))
    for index, package in enumerate(packages):
        x = last_x + 5 + 5 * index
        units = len(package.package.sections) + 1
        placed = Placed(_symbol_for(package), x, 5, unit=units, ref=package.ref, value=package.value, footprint=package.footprint,
                        component=package, texts=[(package.ref, x + 1.6, 4.6, "start")])
        b.symbols.append(placed)
        b.power("VCC", (x, 2))
        b.power("GND", (x, 8))
    return b


def _draw_vref(board: Board) -> Drawing:
    b = _Block(board)
    b.texts.append(("Tierra virtual", 0, -3, 1.8))
    top, bottom = b.two(board.component("R1"), 1, 2, vertical=True)
    b.power("VCC", top)
    top, bottom = b.two(board.component("R2"), 1, 6, vertical=True)
    b.power("GND", bottom)
    top, bottom = b.polar(board.component("C2"), 5, 6, positive_top=True)
    b.power("GND", bottom)
    b.wire((1, 4), (6, 4))
    unit = next(unit for unit in board.units if unit.purpose == "vref")
    pins = b.amp(unit, 10, 4, minus_top=False, text="above")
    b.wire((6, 4), (6, 3), pins["+"])
    b.wire(pins["-"], (7, 6), (14, 6), (14, 4))
    b.wire(pins["out"], (16, 4))
    b.vref((16, 4))
    return b


def _draw_input(board: Board) -> Drawing:
    b = _Block(board)
    b.texts.append(("Entrada", 0, -4, 1.8))
    j2 = board.component("J2")
    b.symbols.append(Placed(CONNECTOR_SYMBOL, 0, 3, ref=j2.ref, value=j2.value, footprint=j2.footprint, component=j2,
                            texts=[(j2.ref, 0.4, 1.2, "middle"), (j2.value, 0.4, 5.6, "middle")]))
    b.power("GND", (2, 4))
    top, bottom = b.polar(board.component("C3"), 4, 0, positive_top=True)
    b.wire((2, 3), (4, 3), bottom)
    top_r, bottom_r = b.two(board.component("R3"), 7, 0, vertical=True)
    b.vref(bottom_r)
    b.wire(top, (7, -2), (9, -2))
    b.labels.append(Label("IN", 9, -2, 0))
    return b


def _draw_output(board: Board) -> Drawing:
    b = _Block(board)
    b.texts.append(("Salida", 0, -4, 1.8))
    b.labels.append(Label("OUT", 0, -2, 180))
    top, bottom = b.polar(board.component("C4"), 3, 0, positive_top=True)
    b.wire((0, -2), top)
    top_r, bottom_r = b.two(board.component("R4"), 6, 5, vertical=True)
    b.power("GND", bottom_r)
    j3 = board.component("J3")
    b.symbols.append(Placed(CONNECTOR_SYMBOL, 12, 3, mirror="y", ref=j3.ref, value=j3.value, footprint=j3.footprint, component=j3,
                            texts=[(j3.ref, 11.6, 1.2, "middle"), (j3.value, 11.6, 5.6, "middle")]))
    b.wire(bottom, (3, 3), (10, 3))
    b.power("GND", (10, 4))
    return b


def _draw_spares(board: Board) -> Drawing | None:
    spares = [unit for unit in board.units if unit.purpose == "spare"]
    if not spares:
        return None
    b = _Block(board)
    b.texts.append(("Secciones sin usar", 0, -1, 1.8))
    for index, unit in enumerate(spares):
        x = 4 + 12 * index
        pins = b.amp(unit, x, 3, minus_top=False, text="above")
        b.vref(pins["+"], up=True)
        b.wire(pins["-"], (x - 3, 5), (x + 4, 5), (x + 4, 3), pins["out"])
    return b


def _draw_holes(board: Board) -> Drawing:
    b = _Block(board)
    b.texts.append(("Montaje", 0, -1, 1.8))
    for index in range(4):
        hole = board.component(f"H{index + 1}")
        b.symbols.append(Placed(HOLE_SYMBOL, 1 + 4 * index, 2, ref=hole.ref, value=hole.value, footprint=hole.footprint, component=hole,
                                texts=[(hole.ref, 1 + 4 * index, 4.4, "middle")]))
    return b


# Sheet ---------------------------------------------------------------------------------------------
PAPERS = [("A4", 297, 210), ("A3", 420, 297), ("A2", 594, 420), ("A1", 841, 594), ("A0", 1189, 841)]
MARGIN = 8


@dataclass(slots=True)
class Schematic:
    drawing: Drawing
    paper: str
    width_mm: float
    height_mm: float
    title: str
    board: Board


def _stage_title(stage: StageCircuit) -> str:
    parts = [f"Etapa {stage.stage.index}", TOPOLOGY_NAMES[stage.topology], f"f0 {format_quantity(stage.stage.natural_frequency_hz, 'Hz')}"]
    if stage.stage.q is not None:
        parts.append(f"Q {stage.stage.q:.3f}")
    return " · ".join(parts)


def build_schematic(board: Board) -> Schematic:
    """Lay out the stage blocks in rows and the board sections below them."""
    blocks = [(_draw_stage(board, stage), _stage_title(stage)) for stage in board.stages]
    widths = [block.bounds()[2] - block.bounds()[0] for block, _ in blocks]
    row_limit = max(max(widths), 150)
    sheet = Drawing()
    x, y, row_height = MARGIN, MARGIN + 4, 0.0
    for (block, title), width in zip(blocks, widths):
        x1, y1, x2, y2 = block.bounds()
        if x > MARGIN and x + width > MARGIN + row_limit:
            x, y, row_height = MARGIN, y + math.ceil(row_height) + 8, 0.0
        moved = block.offset(round(x - x1), round(y - y1) + 3)
        moved.texts.append((title, x, y, 1.8))
        sheet.extend(moved)
        x += math.ceil(width) + 8
        row_height = max(row_height, y2 - y1 + 3)
    y += math.ceil(row_height) + 10
    sections = [_draw_power(board), _draw_vref(board), _draw_input(board), _draw_output(board), _draw_spares(board), _draw_holes(board)]
    x, section_height = MARGIN, 0.0
    for section in [section for section in sections if section is not None]:
        x1, y1, x2, y2 = section.bounds()
        if x > MARGIN and x + (x2 - x1) > MARGIN + row_limit:
            x, y, section_height = MARGIN, y + math.ceil(section_height) + 8, 0.0
        sheet.extend(section.offset(round(x - x1), round(y - y1)))
        x += math.ceil(x2 - x1) + 8
        section_height = max(section_height, y2 - y1)
    _orient_two_pin_parts(sheet, board)
    x1, y1, x2, y2 = sheet.bounds()
    needed_w, needed_h = (x2 + MARGIN) * GRID, (y2 + MARGIN + 14) * GRID
    paper, width_mm, height_mm = next(((name, w, h) for name, w, h in PAPERS if w >= needed_w and h >= needed_h), PAPERS[-1])
    inputs = board.inputs
    title = f"Filtro {KIND_NAMES[inputs.kind]} {inputs.approximation.value.capitalize()} de orden {board.result.order}"
    return Schematic(sheet, paper, width_mm, height_mm, title, board)


# Connectivity ------------------------------------------------------------------------------------
def _point_groups(drawing: Drawing) -> tuple[dict[tuple[int, int], object], callable]:
    """Union of points joined by wires, labels and power symbols (pins are just points here)."""
    parent: dict[object, object] = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a, b):
        parent[find(a)] = find(b)

    keys: set[tuple[int, int]] = set()
    for placed in drawing.symbols:
        for point in placed.pins().values():
            keys.add(_key(point))
            if placed.symbol.power and placed.symbol.pins[0].kind == "power_in":
                union(_key(point), ("net", placed.symbol.pins[0].name))
    for label in drawing.labels:
        keys.add(_key((label.x, label.y)))
        union(_key((label.x, label.y)), ("net", label.name))
    for a, b in drawing.wires:
        keys.add(_key(a))
        keys.add(_key(b))
    for a, b in drawing.wires:
        for key in keys:
            if _on_segment((key[0] / 2, key[1] / 2), a, b):
                union(key, _key(a))
    return {key: find(key) for key in keys}, find


def _orient_two_pin_parts(drawing: Drawing, board: Board) -> None:
    """Turn resistors and capacitors so pad 1 sits on the net the board model gives it.

    The templates place symmetric parts without caring which end is pad 1; this propagates the
    known nets (op amp pins, labels, supplies, connectors) through the parts and flips the reversed
    ones, so KiCad numbers the pads like the netlist.
    """
    groups, find = _point_groups(drawing)
    net_of: dict[object, str] = {}
    pending = []
    for placed in drawing.symbols:
        component = placed.component
        if component is None:
            if placed.symbol.power and placed.symbol.pins[0].kind == "power_in":
                net_of[find(("net", placed.symbol.pins[0].name))] = placed.symbol.pins[0].name
            continue
        pins = placed.pins()
        if component.symbol in ("R", "C"):
            pending.append(placed)
            continue
        for number, point in pins.items():
            net = component.pins.get(number)
            if net:
                net_of[groups[_key(point)]] = net
    for label in drawing.labels:
        net_of[find(("net", label.name))] = label.name
    changed = True
    while pending and changed:
        changed = False
        for placed in list(pending):
            pins = placed.pins()
            group1, group2 = groups[_key(pins["1"])], groups[_key(pins["2"])]
            net1, net2 = placed.component.pins["1"], placed.component.pins["2"]
            known1, known2 = net_of.get(group1), net_of.get(group2)
            if known1 is None and known2 is None:
                continue
            swapped = known1 == net2 or known2 == net1
            if swapped:
                placed.rotation = (placed.rotation + 180) % 360
                group1, group2 = group2, group1
            net_of.setdefault(group1, net1)
            net_of.setdefault(group2, net2)
            pending.remove(placed)
            changed = True


def _on_segment(point: Point, a: Point, b: Point) -> bool:
    (px, py), (ax, ay), (bx, by) = point, a, b
    if ax == bx:
        return abs(px - ax) < 1e-6 and min(ay, by) - 1e-6 <= py <= max(ay, by) + 1e-6
    if ay == by:
        return abs(py - ay) < 1e-6 and min(ax, bx) - 1e-6 <= px <= max(ax, bx) + 1e-6
    raise ValueError(f"cable no ortogonal {a} {b}")


def _key(point: Point) -> tuple[int, int]:
    return round(point[0] * 2), round(point[1] * 2)


@dataclass(slots=True)
class ConnectivityReport:
    nets: dict[tuple[str, str], int]  # (ref, pad) -> group
    problems: list[str]


def check_connectivity(schematic: Schematic) -> ConnectivityReport:
    """Rebuild the nets from the drawing (wires, pins, labels, power symbols) and compare with the board."""
    drawing = schematic.drawing
    parent: dict[object, object] = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(a, b):
        parent[find(a)] = find(b)

    problems: list[str] = []
    points: dict[tuple[int, int], list[object]] = {}
    pin_items: dict[tuple[str, str], object] = {}
    for index, placed in enumerate(drawing.symbols):
        for number, point in placed.pins().items():
            if placed.symbol.power and placed.symbol.pins[0].kind == "power_in":
                # Hidden power inputs join the global net of their name; PWR_FLAG does not.
                item = ("net", placed.symbol.pins[0].name)
            elif placed.symbol.power:
                item = ("flag", index)
            else:
                item = ("pin", placed.ref, number)
                pin_items[(placed.ref, number)] = item
            points.setdefault(_key(point), []).append(item)
    for label in drawing.labels:
        points.setdefault(_key((label.x, label.y)), []).append(("net", label.name))
    for index, (a, b) in enumerate(drawing.wires):
        wire = ("wire", index)
        find(wire)
        for point in (a, b):
            points.setdefault(_key(point), []).append(wire)
    # Everything at the same point is connected; a connection point on a wire's body joins the wire.
    for items in points.values():
        for item in items[1:]:
            union(items[0], item)
    for index, (a, b) in enumerate(drawing.wires):
        for key, items in points.items():
            if _on_segment((key[0] / 2, key[1] / 2), a, b):
                union(("wire", index), items[0])
    # Crossings without a connection and overlapping segments make the drawing ambiguous.
    for i, (a1, b1) in enumerate(drawing.wires):
        for j in range(i + 1, len(drawing.wires)):
            a2, b2 = drawing.wires[j]
            horizontal1, horizontal2 = a1[1] == b1[1], a2[1] == b2[1]
            if horizontal1 != horizontal2:
                h, v = ((a1, b1), (a2, b2)) if horizontal1 else ((a2, b2), (a1, b1))
                cross = (v[0][0], h[0][1])
                if (
                    min(h[0][0], h[1][0]) < cross[0] < max(h[0][0], h[1][0])
                    and min(v[0][1], v[1][1]) < cross[1] < max(v[0][1], v[1][1])
                ):
                    problems.append(f"cables cruzados en {cross}")
            elif (horizontal1 and a1[1] == a2[1]) or (not horizontal1 and a1[0] == a2[0]):
                axis = 0 if horizontal1 else 1
                lo1, hi1 = sorted((a1[axis], b1[axis]))
                lo2, hi2 = sorted((a2[axis], b2[axis]))
                if min(hi1, hi2) - max(lo1, lo2) > 1e-6:
                    problems.append(f"cables encimados en {a1}-{b1} y {a2}-{b2}")
    # Wires must not run through a symbol body.
    for placed in drawing.symbols:
        x1, y1, x2, y2 = placed.body()
        for a, b in drawing.wires:
            if a[1] == b[1] and y1 + 0.05 < a[1] < y2 - 0.05 and min(a[0], b[0]) < x2 - 0.05 and max(a[0], b[0]) > x1 + 0.05:
                problems.append(f"cable sobre {placed.ref} en {a}-{b}")
            if a[0] == b[0] and x1 + 0.05 < a[0] < x2 - 0.05 and min(a[1], b[1]) < y2 - 0.05 and max(a[1], b[1]) > y1 + 0.05:
                problems.append(f"cable sobre {placed.ref} en {a}-{b}")
    groups = {key: find(item) for key, item in pin_items.items()}
    # Compare with the board nets.
    expected: dict[tuple[str, str], str] = {}
    for component in schematic.board.components:
        for pad, net in component.pins.items():
            if net:
                expected[(component.ref, pad)] = net
    for key in expected:
        if key not in groups:
            problems.append(f"pin sin dibujar {key}")
    net_to_group: dict[str, object] = {}
    group_to_net: dict[object, str] = {}
    for key, net in expected.items():
        group = groups.get(key)
        if group is None:
            continue
        if net_to_group.setdefault(net, group) != group:
            problems.append(f"la red {net} quedó partida ({key})")
        if group_to_net.setdefault(group, net) != net:
            problems.append(f"las redes {group_to_net[group]} y {net} quedaron unidas ({key})")
    for key in groups:
        if key not in expected and key[0] and not key[0].startswith("#"):
            group = groups[key]
            if group in group_to_net:
                problems.append(f"pin {key} conectado a {group_to_net[group]} pero no debía")
    return ConnectivityReport({key: id(group) for key, group in groups.items()}, problems)


def kicad_net_names(schematic: Schematic) -> dict[str, str]:
    """Board net -> the name KiCad gives it from this drawing, so the board passes KiCad's parity check.

    KiCad names a net after its strongest driver: a power symbol, then a label (``/NAME`` on the root
    sheet), then a pin: ``Net-(R1-Pad2)`` for unnamed pins, ``Net-(U1A--)`` for named ones, which win
    over unnamed ones; ties go to the lowest name.
    """
    drawing = schematic.drawing
    groups, find = _point_groups(drawing)
    board_net: dict[object, str] = {}
    pin_names: dict[object, list[str]] = {}
    label_names: dict[object, list[str]] = {}
    power_names: dict[object, str] = {}
    for placed in drawing.symbols:
        if placed.symbol.power:
            if placed.symbol.pins[0].kind == "power_in":
                power_names[find(("net", placed.symbol.pins[0].name))] = placed.symbol.pins[0].name
            continue
        if placed.component is None:
            continue
        letter = chr(ord("A") + placed.unit - 1) if placed.symbol.units > 1 else ""
        pin_defs = placed.pin_defs()
        points = placed.pins()
        for pin in pin_defs:
            if pin.kind == "no_connect":
                continue
            group = groups[_key(points[pin.number])]
            net = placed.component.pins.get(pin.number)
            if net:
                board_net[group] = net
            if pin.name in ("", "~"):
                name = f"Net-({placed.ref}{letter}-Pad{pin.number})"
            elif sum(other.name == pin.name for other in pin_defs) > 1:
                name = f"Net-({placed.ref}{letter}-{pin.name}-Pad{pin.number})"
            else:
                name = f"Net-({placed.ref}{letter}-{pin.name})"
            pin_names.setdefault(group, []).append(name)
    for label in drawing.labels:
        label_names.setdefault(find(("net", label.name)), []).append("/" + label.name)
    names: dict[str, str] = {}
    for group, net in board_net.items():
        if group in power_names:
            names[net] = power_names[group]
        elif group in label_names:
            names[net] = min(label_names[group])
        else:
            names[net] = min(pin_names[group], key=lambda name: ("-Pad" in name, name))
    return names


def kicad_unconnected_pads(schematic: Schematic) -> dict[tuple[str, str], str]:
    """(ref, pad) -> net KiCad gives a no-connect pin, ``unconnected-(U1B-NC-Pad1)``; the board puts it on
    the pad so it matches the schematic."""
    pads: dict[tuple[str, str], str] = {}
    for placed in schematic.drawing.symbols:
        if placed.component is None:
            continue
        letter = chr(ord("A") + placed.unit - 1) if placed.symbol.units > 1 else ""
        pin_defs = placed.pin_defs()
        for pin in pin_defs:
            if pin.kind != "no_connect":
                continue
            if sum(other.name == pin.name for other in pin_defs) > 1:
                pads[(placed.ref, pin.number)] = f"unconnected-({placed.ref}{letter}-{pin.name}-Pad{pin.number})"
            else:
                pads[(placed.ref, pin.number)] = f"unconnected-({placed.ref}{letter}-{pin.name})"
    return pads


def junctions(drawing: Drawing) -> list[Point]:
    """Points where three or more connections meet (KiCad draws a dot there)."""
    counts: dict[tuple[int, int], int] = {}
    for placed in drawing.symbols:
        for point in placed.pins().values():
            counts[_key(point)] = counts.get(_key(point), 0) + 1
    for label in drawing.labels:
        counts[_key((label.x, label.y))] = counts.get(_key((label.x, label.y)), 0) + 1
    for a, b in drawing.wires:
        for point in (a, b):
            counts[_key(point)] = counts.get(_key(point), 0) + 1
    result = []
    for key, count in counts.items():
        point = (key[0] / 2, key[1] / 2)
        through = sum(
            2 for a, b in drawing.wires if _on_segment(point, a, b) and point not in (a, b)
        )
        if count + through >= 3:
            # Power symbols stacked on one pin (GND + PWR_FLAG) are not a wire junction.
            wires_here = sum(1 for a, b in drawing.wires if _on_segment(point, a, b))
            if wires_here:
                result.append(point)
    return result


# SVG -----------------------------------------------------------------------------------------------
SVG_STYLE = """
.schematic .w{stroke:var(--sch-wire,#1e2533);stroke-width:.25;fill:none;stroke-linecap:round}
.schematic .s{stroke:var(--sch-part,#1e4fbf);stroke-width:.25;fill:none;stroke-linejoin:round}
.schematic .sf{fill:var(--sch-part,#1e4fbf)}
.schematic .bg{fill:var(--sch-paper,#ffffff)}
.schematic .j{fill:var(--sch-wire,#1e2533)}
.schematic .t{fill:var(--sch-text,#1e2533);font-family:'Segoe UI',system-ui,sans-serif;font-size:1.5px}
.schematic .v{fill:var(--sch-muted,#5d6578);font-family:'Segoe UI',system-ui,sans-serif;font-size:1.4px}
.schematic .l{fill:var(--sch-label,#b45309);font-family:'Segoe UI',system-ui,sans-serif;font-size:1.5px;font-weight:600}
.schematic .h{fill:var(--sch-text,#1e2533);font-family:'Segoe UI',system-ui,sans-serif;font-weight:600}
.schematic .pn{fill:var(--sch-part,#1e4fbf);font-family:'Segoe UI',system-ui,sans-serif;font-size:1.6px;font-weight:700}
.schematic .frame{stroke:var(--sch-frame,#dfe3eb);stroke-width:.3;fill:none}
"""


def _fmt(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return text if text != "-0" else "0"


# The same look as SVG_STYLE, as presentation attributes (Qt's SVG renderer ignores CSS on text).
_INLINE = {
    "w": {"stroke": "#1e2533", "stroke-width": ".25", "fill": "none", "stroke-linecap": "round"},
    "s": {"stroke": "#1e4fbf", "stroke-width": ".25", "fill": "none", "stroke-linejoin": "round"},
    "sf": {"fill": "#1e4fbf"},
    "bg": {"fill": "#ffffff"},
    "j": {"fill": "#1e2533"},
    "t": {"fill": "#1e2533", "font-family": "Segoe UI, sans-serif", "font-size": "1.5"},
    "v": {"fill": "#5d6578", "font-family": "Segoe UI, sans-serif", "font-size": "1.4"},
    "l": {"fill": "#b45309", "font-family": "Segoe UI, sans-serif", "font-size": "1.5", "font-weight": "600"},
    "h": {"fill": "#1e2533", "font-family": "Segoe UI, sans-serif", "font-weight": "600"},
    "pn": {"fill": "#1e4fbf", "font-family": "Segoe UI, sans-serif", "font-size": "1.6", "font-weight": "700"},
    "frame": {"stroke": "#dfe3eb", "stroke-width": ".3", "fill": "none"},
}


def _style(css: str, inline: bool, **overrides: str) -> str:
    """class="..." for browsers, or the equivalent attributes for Qt."""
    if not inline:
        extra = "".join(f' style="{key.replace("_", "-")}:{value}"' for key, value in overrides.items())
        return f'class="{css}"{extra}'
    attributes: dict[str, str] = {}
    for name in css.split():
        attributes.update(_INLINE[name])
    attributes.update({key.replace("_", "-"): value for key, value in overrides.items()})
    return " ".join(f'{key}="{value}"' for key, value in attributes.items())


def _svg_symbol(placed: Placed, inline: bool = False) -> list[str]:
    def xy(x: float, y: float) -> tuple[str, str]:
        dx, dy = _transform(x, y, placed.rotation, placed.mirror)
        return _fmt((placed.x + dx) * GRID), _fmt((placed.y + dy) * GRID)

    def point(x: float, y: float) -> str:
        return ",".join(xy(x, y))

    paper = "#ffffff" if inline else "var(--sch-paper,#fff)"
    out = []
    for graphic in placed.symbol.graphics:
        if graphic[0] == "rect":
            _, x1, y1, x2, y2, filled = graphic
            points = " ".join(point(x, y) for x, y in ((x1, y1), (x2, y1), (x2, y2), (x1, y2)))
            if filled == "background":
                style = _style("s", inline, fill=paper)
            else:
                style = _style("s sf" if filled is True else "s", inline)
            out.append(f'<polygon {style} points="{points}"/>')
        elif graphic[0] == "line":
            _, pts, width, filled = graphic
            tag = "polygon" if filled == "background" else "polyline"
            style = _style("s", inline, fill=paper) if filled == "background" else _style("s", inline)
            out.append(f'<{tag} {style} points="{" ".join(point(x, y) for x, y in pts)}"/>')
        elif graphic[0] == "circle":
            _, x, y, radius = graphic
            cx, cy = xy(x, y)
            out.append(f'<circle {_style("s", inline)} cx="{cx}" cy="{cy}" r="{_fmt(radius)}"/>')
    for pin in placed.pin_defs():
        if pin.hidden or pin.length == 0:
            continue
        direction = {0: (1, 0), 90: (0, 1), 180: (-1, 0), 270: (0, -1)}[pin.angle]
        start = point(pin.x, pin.y)
        end = point(pin.x + direction[0] * pin.length, pin.y + direction[1] * pin.length)
        out.append(f'<polyline {_style("s", inline)} points="{start} {end}"/>')
        if placed.symbol.show_pin_names and pin.name in {"+", "-"}:
            tx, ty = xy(pin.x + 3.4, pin.y)
            sign = "+" if pin.name == "+" else "\u2212"
            out.append(f'<text {_style("pn", inline)} x="{tx}" y="{float(ty) + 0.55:.3f}" text-anchor="middle">{sign}</text>')
    if placed.symbol.unit_pins and placed.unit == placed.symbol.units:
        # Power unit: show the pin names V+ / V-.
        for pin in placed.pin_defs():
            if pin.hidden:
                continue
            tx, ty = xy(pin.x, pin.y - 3.2 if pin.y > 0 else pin.y + 3.2)
            out.append(f'<text {_style("v", inline)} x="{tx}" y="{float(ty) + 0.5:.3f}" text-anchor="middle">{pin.name}</text>')
    for text, x, y, anchor in placed.texts:
        css = "t" if text == placed.ref or (placed.component is not None and text.startswith(placed.ref)) else "v"
        out.append(f'<text {_style(css, inline)} x="{_fmt(x * GRID)}" y="{_fmt(y * GRID)}" text-anchor="{anchor}">{html.escape(text)}</text>')
    return out


def to_svg(schematic: Schematic, standalone: bool = True, inline: bool = False) -> str:
    """SVG of the sheet.

    ``standalone`` keeps the paper size; otherwise the view is cropped to the drawing. ``inline``
    writes plain presentation attributes instead of CSS classes (for Qt's renderer).
    """
    drawing = schematic.drawing
    if standalone:
        left, top, width, height = 0.0, 0.0, schematic.width_mm, schematic.height_mm
    else:
        x1, y1, x2, y2 = drawing.bounds()
        left, top = (x1 - 2) * GRID, (min(y1, MARGIN - 3) - 2) * GRID
        width, height = (x2 + 2) * GRID - left, (y2 + 2) * GRID - top
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_fmt(left)} {_fmt(top)} {_fmt(width)} {_fmt(height)}"'
        + (f' width="{_fmt(width)}mm" height="{_fmt(height)}mm"' if standalone else "")
        + ' class="schematic">',
    ]
    if not inline:
        out.append(f"<style>{SVG_STYLE}</style>")
    out.append(f'<rect {_style("bg", inline)} x="{_fmt(left)}" y="{_fmt(top)}" width="{_fmt(width)}" height="{_fmt(height)}"/>')
    if standalone:
        out.append(f'<rect {_style("frame", inline)} x="5" y="5" width="{_fmt(width - 10)}" height="{_fmt(height - 10)}"/>')
    out.append(f'<text {_style("h", inline)} x="{_fmt(MARGIN * GRID)}" y="{_fmt(MARGIN * GRID - 5)}" font-size="3">{html.escape(schematic.title)}</text>')
    for a, b in drawing.wires:
        out.append(f'<line {_style("w", inline)} x1="{_fmt(a[0] * GRID)}" y1="{_fmt(a[1] * GRID)}" x2="{_fmt(b[0] * GRID)}" y2="{_fmt(b[1] * GRID)}"/>')
    for x, y in junctions(drawing):
        out.append(f'<circle {_style("j", inline)} cx="{_fmt(x * GRID)}" cy="{_fmt(y * GRID)}" r=".5"/>')
    for placed in drawing.symbols:
        out.extend(_svg_symbol(placed, inline))
    for label in drawing.labels:
        anchor = "start" if label.angle == 0 else "end"
        dx = 0.4 if label.angle == 0 else -0.4
        out.append(
            f'<text {_style("l", inline)} x="{_fmt(label.x * GRID + dx)}" y="{_fmt(label.y * GRID - 0.5)}" text-anchor="{anchor}">{html.escape(label.name)}</text>'
        )
    for text, x, y, size in drawing.texts:
        out.append(f'<text {_style("h", inline)} x="{_fmt(x * GRID)}" y="{_fmt(y * GRID)}" font-size="{_fmt(size)}">{html.escape(text)}</text>')
    out.append("</svg>")
    return "\n".join(out)


# KiCad ---------------------------------------------------------------------------------------------
_NAMESPACE = uuid.UUID("6f1c2d8e-1d2b-4c55-9a3e-50f1a7e0c0de")


class _Ids:
    """Deterministic UUIDs, so the same design always gives the same file."""

    def __init__(self, seed: str) -> None:
        self.seed = seed
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        return str(uuid.uuid5(_NAMESPACE, f"{self.seed}/{self.count}"))


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _effects(hidden: bool = False, justify: str | None = None, size: float = 1.27) -> str:
    parts = [f"(font (size {_fmt(size)} {_fmt(size)}))"]
    if justify:
        parts.append(f"(justify {justify})")
    if hidden:
        parts.append("hide")
    return f"(effects {' '.join(parts)})"


def _kicad_graphic(graphic: tuple) -> str:
    if graphic[0] == "rect":
        _, x1, y1, x2, y2, filled = graphic
        fill = "outline" if filled is True else ("background" if filled == "background" else "none")
        return f"(rectangle (start {_fmt(x1)} {_fmt(y1)}) (end {_fmt(x2)} {_fmt(y2)}) (stroke (width 0.254) (type default)) (fill (type {fill})))"
    if graphic[0] == "line":
        _, pts, width, filled = graphic
        fill = "background" if filled == "background" else "none"
        xy = " ".join(f"(xy {_fmt(x)} {_fmt(y)})" for x, y in pts)
        return f"(polyline (pts {xy}) (stroke (width {_fmt(width)}) (type default)) (fill (type {fill})))"
    _, x, y, radius = graphic
    return f"(circle (center {_fmt(x)} {_fmt(y)}) (radius {_fmt(radius)}) (stroke (width 0.254) (type default)) (fill (type none)))"


def _kicad_pin(pin: PinDef) -> str:
    hide = " hide" if pin.hidden else ""
    return (
        f"(pin {pin.kind} line (at {_fmt(pin.x)} {_fmt(pin.y)} {pin.angle}) (length {_fmt(pin.length)}){hide} "
        f"(name {_q(pin.name)} {_effects()}) (number {_q(pin.number)} {_effects()}))"
    )


def _kicad_lib_symbol(symbol: SymbolDef, prefix: str = "SOFIA:") -> str:
    name = symbol.name
    lines = [f"(symbol {_q(prefix + name)}"]
    if symbol.power:
        lines.append("(power)")
    lines.append("(pin_numbers hide)" if not symbol.unit_pins else "")
    lines.append(f"(pin_names (offset {'0.254' if symbol.show_pin_names else '0'}){'' if symbol.show_pin_names else ' hide'})")
    lines.append("(exclude_from_sim no) (in_bom yes) (on_board yes)")
    value = symbol.pins[0].name if symbol.power else name
    lines.append(f"(property \"Reference\" {_q(symbol.reference)} (at 0 0 0) {_effects(hidden=symbol.power)})")
    lines.append(f"(property \"Value\" {_q(value)} (at 0 0 0) {_effects()})")
    lines.append(f"(property \"Footprint\" \"\" (at 0 0 0) {_effects(hidden=True)})")
    lines.append(f"(property \"Datasheet\" \"~\" (at 0 0 0) {_effects(hidden=True)})")
    if symbol.unit_pins:
        lines.append(f"(symbol {_q(name + '_0_1')} " + " ".join(_kicad_graphic(g) for g in []) + ")")
        for unit, pins in symbol.unit_pins.items():
            graphics = POWER_UNIT_GRAPHICS if unit == symbol.units else symbol.graphics
            body = " ".join(_kicad_graphic(g) for g in graphics)
            lines.append(f"(symbol {_q(f'{name}_{unit}_1')} {body} {' '.join(_kicad_pin(pin) for pin in pins)})")
    else:
        lines.append(f"(symbol {_q(name + '_0_1')} {' '.join(_kicad_graphic(g) for g in symbol.graphics)})")
        lines.append(f"(symbol {_q(name + '_1_1')} {' '.join(_kicad_pin(pin) for pin in symbol.pins)})")
    lines.append(")")
    return " ".join(line for line in lines if line)


# The reference is driven by an op amp output, so in KiCad it is a global label: a power symbol there
# would need a PWR_FLAG, and KiCad's ERC rejects a PWR_FLAG on an op amp output.
LABEL_SYMBOLS = ("VREF", "VREF_UP")


def kicad_symbol_library(schematic: Schematic) -> str:
    """SOFIA.kicad_sym with the symbols the schematic uses (the project's symbol library)."""
    used = {placed.symbol.name: placed.symbol for placed in schematic.drawing.symbols if placed.symbol.name not in LABEL_SYMBOLS}
    lines = ["(kicad_symbol_lib", "\t(version 20231120)", '\t(generator "sofia_filter_studio")', f"\t(generator_version {_q(__version__)})"]
    lines += [f"\t{_kicad_lib_symbol(symbol, prefix='')}" for symbol in used.values()]
    lines.append(")")
    return "\n".join(lines) + "\n"


def _global_label(placed: Placed, ids: "_Ids") -> str:
    (px, py), = placed.pins().values()
    x1, y1, x2, y2 = placed.body()
    dx, dy = (x1 + x2) / 2 - px, (y1 + y2) / 2 - py
    if abs(dy) >= abs(dx):
        angle = 270 if dy > 0 else 90
    else:
        angle = 0 if dx > 0 else 180
    justify = "left" if angle in (0, 90) else "right"
    x, y = _fmt(px * GRID), _fmt(py * GRID)
    return (
        f"\t(global_label {_q(placed.symbol.pins[0].name)} (shape passive) (at {x} {y} {angle}) (fields_autoplaced yes) "
        f"{_effects(justify=justify)} (uuid {_q(ids())}) "
        f"(property \"Intersheetrefs\" \"${{INTERSHEET_REFS}}\" (at {x} {y} 0) {_effects(hidden=True, justify=justify)}))"
    )


def to_kicad(schematic: Schematic, project: str = "sofia") -> str:
    """KiCad 8 schematic (.kicad_sch); the symbols travel inside the file."""
    drawing = schematic.drawing
    ids = _Ids(schematic.title + "|" + "|".join(component.ref + component.value for component in schematic.board.components))
    root = ids()
    used: dict[str, SymbolDef] = {}
    for placed in drawing.symbols:
        if placed.symbol.name not in LABEL_SYMBOLS:
            used[placed.symbol.name] = placed.symbol
    out = [
        "(kicad_sch",
        "\t(version 20231120)",
        '\t(generator "sofia_filter_studio")',
        f"\t(generator_version {_q(__version__)})",
        f"\t(uuid {_q(root)})",
        f"\t(paper {_q(schematic.paper)})",
        f"\t(title_block (title {_q(schematic.title)}) (rev {_q(__version__)}) (company \"SOFIA Filter Studio\"))",
        "\t(lib_symbols",
    ]
    out += [f"\t\t{_kicad_lib_symbol(symbol)}" for symbol in used.values()]
    out.append("\t)")
    for x, y in junctions(drawing):
        out.append(f"\t(junction (at {_fmt(x * GRID)} {_fmt(y * GRID)}) (diameter 0) (color 0 0 0 0) (uuid {_q(ids())}))")
    for a, b in drawing.wires:
        out.append(
            f"\t(wire (pts (xy {_fmt(a[0] * GRID)} {_fmt(a[1] * GRID)}) (xy {_fmt(b[0] * GRID)} {_fmt(b[1] * GRID)})) "
            f"(stroke (width 0) (type default)) (uuid {_q(ids())}))"
        )
    for label in drawing.labels:
        justify = "left bottom" if label.angle == 0 else "right bottom"
        out.append(
            f"\t(label {_q(label.name)} (at {_fmt(label.x * GRID)} {_fmt(label.y * GRID)} {label.angle}) "
            f"(fields_autoplaced yes) {_effects(justify=justify)} (uuid {_q(ids())}))"
        )
    for text, x, y, size in drawing.texts:
        out.append(f"\t(text {_q(text)} (exclude_from_sim no) (at {_fmt(x * GRID)} {_fmt(y * GRID)} 0) {_effects(justify='left bottom', size=size)} (uuid {_q(ids())}))")
    power_count = 0
    for placed in drawing.symbols:
        symbol = placed.symbol
        if symbol.name in LABEL_SYMBOLS:
            out.append(_global_label(placed, ids))
            continue
        if symbol.power:
            power_count += 1
            reference = f"{symbol.reference}0{power_count:02d}"
            value = symbol.pins[0].name
        else:
            reference = placed.ref
            value = placed.value
        mirror = f" (mirror {placed.mirror})" if placed.mirror else ""
        x, y = placed.x * GRID, placed.y * GRID
        in_bom = "no" if symbol.power or (placed.component is not None and not placed.component.in_bom) else "yes"
        texts = {text: (tx, ty, anchor) for text, tx, ty, anchor in placed.texts}
        ref_text = texts.get(placed.ref) or next((v for k, v in texts.items() if k.startswith(placed.ref)), None)
        value_text = texts.get(value)

        # KiCad turns a field with its symbol: on a symbol at 90 or 270 degrees a field at 90 reads
        # horizontally. Text that would end up upside down (180) is turned over, which swaps its justification.
        field_angle = 90 if placed.rotation % 180 == 90 else 0
        upside_down = (placed.rotation + field_angle) % 360 == 180

        def at(position, hidden):
            if position is None:
                return f"(at {_fmt(x)} {_fmt(y)} {field_angle}) {_effects(hidden=True)}"
            tx, ty, anchor = position
            if upside_down:
                anchor = {"start": "end", "end": "start"}.get(anchor, anchor)
            justify = {"start": "left", "end": "right", "middle": None}[anchor]
            return f"(at {_fmt(tx * GRID)} {_fmt(ty * GRID - 0.6)} {field_angle}) {_effects(hidden=hidden, justify=justify)}"

        lines = [
            f"\t(symbol (lib_id {_q('SOFIA:' + symbol.name)}) (at {_fmt(x)} {_fmt(y)} {placed.rotation}){mirror} (unit {placed.unit})",
            f"\t\t(exclude_from_sim no) (in_bom {in_bom}) (on_board yes) (dnp no) (uuid {_q(ids())})",
            f"\t\t(property \"Reference\" {_q(reference)} {at(ref_text, symbol.power)})",
            f"\t\t(property \"Value\" {_q(value)} {at(value_text, symbol.name == 'PWR_FLAG')})",
            f"\t\t(property \"Footprint\" {_q(placed.footprint)} (at {_fmt(x)} {_fmt(y)} 0) {_effects(hidden=True)})",
            f"\t\t(property \"Datasheet\" \"~\" (at {_fmt(x)} {_fmt(y)} 0) {_effects(hidden=True)})",
        ]
        if placed.component is not None and placed.component.description:
            lines.append(f"\t\t(property \"Description\" {_q(placed.component.description)} (at {_fmt(x)} {_fmt(y)} 0) {_effects(hidden=True)})")
        for pin in placed.pin_defs():
            lines.append(f"\t\t(pin {_q(pin.number)} (uuid {_q(ids())}))")
        lines.append(f"\t\t(instances (project {_q(project)} (path {_q('/' + root)} (reference {_q(reference)}) (unit {placed.unit}))))")
        lines.append("\t)")
        out.extend(lines)
    out.append('\t(sheet_instances (path "/" (page "1")))')
    out.append(")")
    return "\n".join(out) + "\n"
