"""Printed circuit board: placement guided by the schematic, routing and design-rule check.

The schematic already keeps connected parts together, so its positions (scaled) are the starting
placement; overlaps are then pushed apart. Connectors go to the board edges and each decoupling
capacitor next to its op amp. The router lays the tracks; ``check_design_rules`` then measures the
real copper (not the routing grid) for clearances and connectivity.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .board import Board, Component, Mounting
from .footprints import FOOTPRINTS, Footprint
from .geometry import Shape, circle, distance, pad_shape
from .router import Router, Rules, Terminal, Track, Via

EDGE_MARGIN = 7.0  # room for the corner mounting holes


@dataclass(slots=True)
class PlacedFootprint:
    component: Component
    footprint: Footprint
    x: float  # footprint origin on the board (mm, y down)
    y: float

    def pads(self):
        for pad in self.footprint.pads:
            yield pad, self.x + pad.x, self.y + pad.y, self.component.pins.get(pad.number, "")

    def courtyard(self, margin: float = 0.0) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = self.footprint.courtyard
        return self.x + x1 - margin, self.y + y1 - margin, self.x + x2 + margin, self.y + y2 + margin

    def center(self) -> tuple[float, float]:
        cx, cy = self.footprint.center()
        return self.x + cx, self.y + cy


@dataclass(slots=True)
class Pcb:
    board: Board
    footprints: list[PlacedFootprint]
    outline: tuple[float, float, float, float]
    rules: Rules
    tracks: list[Track] = field(default_factory=list)
    vias: list[Via] = field(default_factory=list)
    unrouted: list = field(default_factory=list)
    problems: list[str] = field(default_factory=list)

    @property
    def width(self) -> float:
        return self.outline[2] - self.outline[0]

    @property
    def height(self) -> float:
        return self.outline[3] - self.outline[1]

    def footprint(self, ref: str) -> PlacedFootprint:
        return next(placed for placed in self.footprints if placed.component.ref == ref)

    def nets(self) -> list[str]:
        names = {net for placed in self.footprints for _, _, _, net in placed.pads() if net}
        return ["GND"] + sorted(names - {"GND"}) if "GND" in names else sorted(names)


# Placement ---------------------------------------------------------------------------------------
def _snap(value: float, grid: float) -> float:
    return round(value / grid) * grid


def _resolve_overlaps(placed: list[PlacedFootprint], gap: float, fixed: set[str], rounds: int = 400) -> None:
    for _ in range(rounds):
        moved = False
        for a_index in range(len(placed)):
            a = placed[a_index]
            ax1, ay1, ax2, ay2 = a.courtyard(gap / 2)
            for b in placed[a_index + 1 :]:
                bx1, by1, bx2, by2 = b.courtyard(gap / 2)
                overlap_x = min(ax2, bx2) - max(ax1, bx1)
                overlap_y = min(ay2, by2) - max(ay1, by1)
                if overlap_x <= 0 or overlap_y <= 0:
                    continue
                moved = True
                a_fixed, b_fixed = a.component.ref in fixed, b.component.ref in fixed
                share_a = 0.0 if a_fixed else (1.0 if b_fixed else 0.5)
                share_b = 1.0 - share_a if not b_fixed else 0.0
                (acx, acy), (bcx, bcy) = a.center(), b.center()
                if overlap_x < overlap_y:
                    sign = -1 if acx < bcx or (acx == bcx and a_index % 2) else 1
                    a.x += sign * overlap_x * share_a
                    b.x -= sign * overlap_x * share_b
                else:
                    sign = -1 if acy < bcy or (acy == bcy and a_index % 2) else 1
                    a.y += sign * overlap_y * share_a
                    b.y -= sign * overlap_y * share_b
                ax1, ay1, ax2, ay2 = a.courtyard(gap / 2)
        if not moved:
            return


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> tuple[float, float]:
    return min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])


def _settle_on_grid(placed: list[PlacedFootprint], gap: float, grid: float, rounds: int = 40) -> None:
    """Snapping to the grid can bring two parts closer than ``gap`` (the room for a reference). Push one
    of them away a whole number of grid steps, so everything stays on the grid, and only where that does
    not put it on top of a third part."""

    def clashes(item: PlacedFootprint) -> bool:
        box = item.courtyard()
        return any(min(_overlaps(box, other.courtyard())) > 1e-6 for other in placed if other is not item)

    for _ in range(rounds):
        moved = False
        for a_index, a in enumerate(placed):
            for b in placed[a_index + 1 :]:
                overlap_x, overlap_y = _overlaps(a.courtyard(gap / 2), b.courtyard(gap / 2))
                if overlap_x <= 1e-6 or overlap_y <= 1e-6:
                    continue
                (acx, acy), (bcx, bcy) = a.center(), b.center()
                if overlap_x < overlap_y:
                    shift = (math.ceil(overlap_x / grid - 1e-6) * grid * (1 if bcx >= acx else -1), 0.0)
                else:
                    shift = (0.0, math.ceil(overlap_y / grid - 1e-6) * grid * (1 if bcy >= acy else -1))
                for item, sign in ((b, 1), (a, -1)):
                    item.x += sign * shift[0]
                    item.y += sign * shift[1]
                    if not clashes(item):
                        moved = True
                        break
                    item.x -= sign * shift[0]
                    item.y -= sign * shift[1]
        if not moved:
            return


def place(board: Board, schematic=None, spread: float = 1.0) -> list[PlacedFootprint]:
    """Islands: each op amp package with its resistors and capacitors next to the pins they use.

    Islands follow the signal (package order) in rows; the supply and input connectors go to the
    left edge and the output connector to the right one.
    """
    smd = board.options.mounting is Mounting.SMD
    # Room above every part for its reference on the silkscreen.
    gap = (1.4 if smd else 1.6) * spread
    grid = 0.635
    by_ref = {component.ref: component for component in board.components}
    packages = [component for component in board.components if component.symbol == "OPAMP"]
    pad_stage: dict[tuple[str, str], int] = {}
    for unit in board.units:
        stage = unit.part.stage if unit.part is not None else 0
        for pad in unit.component.package.sections[unit.unit - 1]:
            pad_stage[(unit.component.ref, pad)] = stage
    quiet = {"VCC", "GND", "VREF", ""}

    def size(component: Component) -> tuple[float, float]:
        x1, y1, x2, y2 = FOOTPRINTS[component.footprint].courtyard
        return x2 - x1, y2 - y1

    # Which package (and pin) each resistor or capacitor belongs to.
    attached: dict[str, list[tuple[Component, str]]] = {package.ref: [] for package in packages}
    loose: list[Component] = []
    decoupling = {f"C{number}": package for number, package in enumerate(packages, start=5)}
    for component in board.components:
        if component.symbol not in ("R", "C", "CP") or component.ref in decoupling:
            continue
        nets = set(component.pins.values()) - quiet
        best = None
        for package in packages:
            for pad, net in package.pins.items():
                if net in nets:
                    score = 2 if pad_stage.get((package.ref, pad)) == component.stage else 1
                    if best is None or score > best[0]:
                        best = (score, package, pad)
        if best is None or component.ref in ("C1", "C3", "R3", "C4", "R4"):
            loose.append(component)
        else:
            attached[best[1].ref].append((component, best[2]))

    centers: dict[str, tuple[float, float]] = {}
    islands: list[tuple[list[str], tuple[float, float, float, float]]] = []
    for package in packages:
        footprint = FOOTPRINTS[package.footprint]
        fx, fy = footprint.center()
        px1, py1, px2, py2 = footprint.courtyard
        local = {package.ref: (0.0, 0.0)}
        pads = {pad.number: (pad.x - fx, pad.y - fy) for pad in footprint.pads}
        sides = {"left": [], "right": []}
        for component, pad in attached[package.ref]:
            sides["left" if pads[pad][0] < 0 else "right"].append((pads[pad][1], component))
        half_w, half_h = (px2 - px1) / 2, (py2 - py1) / 2
        for side, items in sides.items():
            items.sort(key=lambda item: item[0])
            per_column = max(3, math.ceil((2 * half_h + gap) / (size(items[0][1])[1] + gap)) + 1) if items else 3
            columns = [items[k : k + per_column] for k in range(0, len(items), per_column)]
            offset = half_w + gap
            for column in columns:
                width = max(size(component)[0] for _, component in column)
                heights = [size(component)[1] for _, component in column]
                # Whole grid steps between centers: snapping then moves the column as one piece and
                # keeps the gap above every part for its reference.
                ys = [0.0]
                for previous, height in zip(heights, heights[1:]):
                    ys.append(ys[-1] + math.ceil(((previous + height) / 2 + gap) / grid - 1e-9) * grid)
                x = offset + width / 2
                for (_, component), y in zip(column, ys):
                    local[component.ref] = (-x if side == "left" else x, y - ys[-1] / 2)
                offset += width + gap
        cap = by_ref.get(next(ref for ref, owner in decoupling.items() if owner is package))
        if cap is not None:
            local[cap.ref] = (0.0, -math.ceil((half_h + gap + size(cap)[1] / 2) / grid - 1e-9) * grid)
        boxes = []
        for ref, (x, y) in local.items():
            w, h = size(by_ref[ref])
            boxes.append((x - w / 2, y - h / 2, x + w / 2, y + h / 2))
        bounds = (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))
        islands.append((list(local), bounds))
        for ref, point in local.items():
            centers[ref] = point
    # Rows of islands, about 1.6 times wider than tall.
    area = sum((b[2] - b[0] + 2 * gap) * (b[3] - b[1] + 2 * gap) for _, b in islands)
    row_limit = max(math.sqrt(area * 1.8), max(b[2] - b[0] for _, b in islands))
    x = y = 0.0
    row_height = 0.0
    island_gap = (2.0 if smd else 3.0) * spread
    last_center = (0.0, 0.0)
    for refs, (bx1, by1, bx2, by2) in islands:
        width, height = bx2 - bx1, by2 - by1
        if x > 0 and x + width > row_limit:
            x, y, row_height = 0.0, y + row_height + island_gap, 0.0
        dx, dy = x - bx1, y - by1
        for ref in refs:
            cx, cy = centers[ref]
            centers[ref] = (cx + dx, cy + dy)
        last_center = (x + width / 2, y + height / 2)
        x += width + island_gap
        row_height = max(row_height, height)
    total_w = max((centers[ref][0] for refs, _ in islands for ref in refs), default=0.0)
    # Edge columns: supply and input on the left, output on the right.
    left = [by_ref[ref] for ref in ("J1", "C1", "J2", "C3", "R3")] + [component for component in loose if component.ref not in ("J1", "C1", "J2", "C3", "R3", "C4", "R4")]
    column_w = max(size(component)[0] for component in left)
    lx = -island_gap - column_w / 2 - (4.0 if smd else 6.0)
    ly = 0.0
    for component in left:
        h = size(component)[1]
        centers[component.ref] = (lx, ly + h / 2)
        ly += h + gap * 1.5
    right = [by_ref[ref] for ref in ("C4", "R4", "J3")]
    rx = total_w + island_gap + max(size(component)[0] for component in right) / 2 + (8.0 if smd else 12.0)
    heights = [size(component)[1] for component in right]
    ry = last_center[1] - (sum(heights) + gap * 1.5 * (len(right) - 1)) / 2
    for component, h in zip(right, heights):
        centers[component.ref] = (rx, ry + h / 2)
        ry += h + gap * 1.5
    placed = []
    for ref, (cx, cy) in centers.items():
        component = by_ref[ref]
        footprint = FOOTPRINTS[component.footprint]
        fx, fy = footprint.center()
        placed.append(PlacedFootprint(component, footprint, _snap(cx - fx, grid), _snap(cy - fy, grid)))
    _resolve_overlaps(placed, gap, fixed=set())
    for item in placed:
        item.x = _snap(item.x, grid)
        item.y = _snap(item.y, grid)
    _resolve_overlaps(placed, gap, fixed=set(), rounds=60)
    for item in placed:
        item.x = _snap(item.x, grid)
        item.y = _snap(item.y, grid)
    _settle_on_grid(placed, gap, grid)
    return placed


def _outline(placed: list[PlacedFootprint]) -> tuple[float, float, float, float]:
    boxes = [item.courtyard() for item in placed if item.component.symbol != "HOLE"]
    x1 = min(box[0] for box in boxes) - EDGE_MARGIN
    y1 = min(box[1] for box in boxes) - EDGE_MARGIN
    x2 = max(box[2] for box in boxes) + EDGE_MARGIN
    y2 = max(box[3] for box in boxes) + EDGE_MARGIN
    return _snap(x1, 0.635), _snap(y1, 0.635), _snap(x2, 0.635), _snap(y2, 0.635)


def _with_holes(board: Board, placed: list[PlacedFootprint], outline) -> list[PlacedFootprint]:
    x1, y1, x2, y2 = outline
    corners = [(x1 + 3.5, y1 + 3.5), (x2 - 3.5, y1 + 3.5), (x1 + 3.5, y2 - 3.5), (x2 - 3.5, y2 - 3.5)]
    holes = []
    for number, (x, y) in enumerate(corners, start=1):
        component = board.component(f"H{number}")
        holes.append(PlacedFootprint(component, FOOTPRINTS[component.footprint], x, y))
    return [item for item in placed if item.component.symbol != "HOLE"] + holes


def _normalize(placed: list[PlacedFootprint], outline) -> tuple[list[PlacedFootprint], tuple[float, float, float, float]]:
    """Move everything so the board's top-left corner sits at (10, 10) mm."""
    dx, dy = 10 - outline[0], 10 - outline[1]
    for item in placed:
        item.x += dx
        item.y += dy
    x1, y1, x2, y2 = outline
    return placed, (x1 + dx, y1 + dy, x2 + dx, y2 + dy)


# Routing ---------------------------------------------------------------------------------------
def _terminals(placed: list[PlacedFootprint]) -> tuple[list[Terminal], list[Shape]]:
    terminals, obstacles = [], []
    for item in placed:
        for pad, x, y, net in item.pads():
            shape = pad_shape(pad.shape, x, y, pad.w, pad.h)
            if not pad.plated:
                obstacles.append(circle(x, y, max(pad.w, pad.h) / 2 + 2.6))  # screw head keep-out
            elif not net:
                obstacles.append(shape)
            else:
                terminals.append(Terminal((item.component.ref, pad.number), net, shape, (0, 1) if pad.tht else (0,), x, y))
    return terminals, obstacles


def build_pcb(board: Board, schematic=None, rules: Rules | None = None) -> Pcb:
    """Place, route (with retries) and check the board."""
    from .schematic import build_schematic

    rules = rules or Rules()
    schematic = schematic or build_schematic(board)
    best: Pcb | None = None
    for spread in (1.0, 1.25, 1.55):
        placed = place(board, schematic, spread)
        outline = _outline(placed)
        placed, outline = _normalize(_with_holes(board, placed, outline), outline)
        terminals, obstacles = _terminals(placed)
        router = Router(outline, terminals, obstacles, rules)
        order = router.default_order()
        for _attempt in range(3):
            result = router.route(order)
            pcb = Pcb(board, placed, outline, rules, result.tracks, result.vias, result.unrouted)
            if best is None or len(pcb.unrouted) < len(best.unrouted):
                best = pcb
            if not result.unrouted:
                break
            failed = list(dict.fromkeys(net for net, _, _ in result.unrouted))
            order = failed + [net for net in order if net not in failed]
        if not best.unrouted:
            break
    best.problems = check_design_rules(best)
    return best


# Design-rule check -------------------------------------------------------------------------------
@dataclass(slots=True)
class _Copper:
    net: str | None
    layers: tuple[int, ...]
    shape: Shape
    label: str
    pad: tuple[str, str] | None = None


def copper_items(pcb: Pcb) -> list[_Copper]:
    items: list[_Copper] = []
    for item in pcb.footprints:
        for pad, x, y, net in item.pads():
            if not pad.plated:
                continue
            label = f"{item.component.ref}.{pad.number}"
            items.append(_Copper(net or f"(sin red) {label}", (0, 1) if pad.tht else (0,), pad_shape(pad.shape, x, y, pad.w, pad.h), label, (item.component.ref, pad.number)))
    from .geometry import Capsule

    for track in pcb.tracks:
        shape = Capsule(track.x1, track.y1, track.x2, track.y2, track.width / 2)
        items.append(_Copper(track.net, (track.layer,), shape, f"pista {track.net}"))
    for via in pcb.vias:
        items.append(_Copper(via.net, (0, 1), circle(via.x, via.y, via.diameter / 2), f"vía {via.net}"))
    return items


def check_design_rules(pcb: Pcb) -> list[str]:
    """Clearance between different nets, distance to the edge, holes, and that every net is joined."""
    rules = pcb.rules
    items = copper_items(pcb)
    problems: list[str] = []
    cell = 3.0
    grid: dict[tuple[int, int], list[int]] = {}
    for index, item in enumerate(items):
        x1, y1, x2, y2 = item.shape.bounds()
        for cx in range(math.floor(x1 / cell), math.floor(x2 / cell) + 1):
            for cy in range(math.floor(y1 / cell), math.floor(y2 / cell) + 1):
                grid.setdefault((cx, cy), []).append(index)
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    checked: set[tuple[int, int]] = set()
    for members in grid.values():
        for a_pos, a in enumerate(members):
            for b in members[a_pos + 1 :]:
                pair = (a, b) if a < b else (b, a)
                if pair in checked:
                    continue
                checked.add(pair)
                first, second = items[a], items[b]
                if not set(first.layers) & set(second.layers):
                    continue
                gap = distance(first.shape, second.shape)
                if first.net == second.net:
                    if gap <= 1e-6:
                        parent[find(a)] = find(b)
                elif gap < rules.clearance - 1e-6:
                    problems.append(f"separación de {gap:.3f} mm entre {first.label} y {second.label}")
    x1, y1, x2, y2 = pcb.outline
    for item in items:
        bx1, by1, bx2, by2 = item.shape.bounds()
        if bx1 - x1 < rules.edge - 1e-6 or by1 - y1 < rules.edge - 1e-6 or x2 - bx2 < rules.edge - 1e-6 or y2 - by2 < rules.edge - 1e-6:
            problems.append(f"{item.label} queda a menos de {rules.edge} mm del borde")
    groups: dict[str, set[int]] = {}
    for index, item in enumerate(items):
        if item.pad is not None and item.net and not item.net.startswith("(sin red)"):
            groups.setdefault(item.net, set()).add(find(index))
    for net, roots in groups.items():
        if len(roots) > 1:
            problems.append(f"la red {net} queda en {len(roots)} partes sin unir")
    # Mounting holes against copper.
    for item in pcb.footprints:
        for pad, x, y, _ in item.pads():
            if pad.plated:
                continue
            hole = circle(x, y, pad.w / 2)
            for copper in items:
                if distance(hole, copper.shape) < rules.clearance - 1e-6:
                    problems.append(f"{copper.label} muy cerca del barreno {item.component.ref}")
    return problems


# Preview -----------------------------------------------------------------------------------------
def to_svg(pcb: Pcb, side: str = "top") -> str:
    """Board preview: copper, pads, holes, outline and reference designators."""
    x1, y1, x2, y2 = pcb.outline
    pad_margin = 2
    view = f"{x1 - pad_margin} {y1 - pad_margin} {x2 - x1 + 2 * pad_margin} {y2 - y1 + 2 * pad_margin}"
    front, back = ("#c2410c", "#2563eb") if side == "top" else ("#2563eb", "#c2410c")
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view}" class="pcb">',
        f'<rect x="{x1}" y="{y1}" width="{x2 - x1}" height="{y2 - y1}" rx="1" fill="#0f5132" stroke="#e8d27a" stroke-width="0.25"/>',
    ]
    layers = (1, 0) if side == "top" else (0, 1)
    for layer in layers:
        color = "#3b82f6" if layer == 1 else "#f59e0b"
        opacity = "0.55" if (layer == 1) == (side == "top") else "0.95"
        for track in pcb.tracks:
            if track.layer == layer:
                out.append(
                    f'<line x1="{track.x1:.3f}" y1="{track.y1:.3f}" x2="{track.x2:.3f}" y2="{track.y2:.3f}" stroke="{color}" '
                    f'stroke-opacity="{opacity}" stroke-width="{track.width}" stroke-linecap="round"/>'
                )
    for item in pcb.footprints:
        for pad, x, y, _ in item.pads():
            if not pad.plated:
                out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{pad.w / 2:.3f}" fill="#111827"/>')
                continue
            fill = "#e5c07b" if pad.tht or side == "top" else "#1f2937"
            if pad.shape in ("rect", "roundrect"):
                out.append(f'<rect x="{x - pad.w / 2:.3f}" y="{y - pad.h / 2:.3f}" width="{pad.w}" height="{pad.h}" rx="{pad.rratio * min(pad.w, pad.h) if pad.shape == "roundrect" else 0:.3f}" fill="{fill}"/>')
            else:
                radius = min(pad.w, pad.h) / 2
                out.append(f'<rect x="{x - pad.w / 2:.3f}" y="{y - pad.h / 2:.3f}" width="{pad.w}" height="{pad.h}" rx="{radius}" fill="{fill}"/>')
            if pad.tht:
                out.append(f'<circle cx="{x:.3f}" cy="{y:.3f}" r="{pad.drill / 2:.3f}" fill="#111827"/>')
    for via in pcb.vias:
        out.append(f'<circle cx="{via.x:.3f}" cy="{via.y:.3f}" r="{via.diameter / 2}" fill="#e5c07b"/><circle cx="{via.x:.3f}" cy="{via.y:.3f}" r="{via.drill / 2}" fill="#111827"/>')
    if side == "top":
        for item in pcb.footprints:
            for line in item.footprint.silk:
                points = " ".join(f"{item.x + x:.3f},{item.y + y:.3f}" for x, y in line)
                out.append(f'<polyline points="{points}" fill="none" stroke="#f8fafc" stroke-width="0.15"/>')
            for cx, cy, radius in item.footprint.silk_circles:
                out.append(f'<circle cx="{item.x + cx:.3f}" cy="{item.y + cy:.3f}" r="{radius}" fill="none" stroke="#f8fafc" stroke-width="0.15"/>')
            if item.component.symbol != "HOLE":
                cx, cy = item.center()
                _, cy1, _, _ = item.courtyard()
                out.append(f'<text x="{cx:.3f}" y="{cy1 - 0.25:.3f}" font-size="1" fill="#f8fafc" text-anchor="middle" font-family="sans-serif">{item.component.ref}</text>')
    for net, a, b in pcb.unrouted:
        pa = next(((x, y) for item in pcb.footprints for pad, x, y, _ in item.pads() if (item.component.ref, pad.number) == a), None)
        pb = next(((x, y) for item in pcb.footprints for pad, x, y, _ in item.pads() if (item.component.ref, pad.number) == b), None)
        if pa and pb:
            out.append(f'<line x1="{pa[0]:.3f}" y1="{pa[1]:.3f}" x2="{pb[0]:.3f}" y2="{pb[1]:.3f}" stroke="#f43f5e" stroke-width="0.2" stroke-dasharray="0.6 0.4"/>')
    out.append("</svg>")
    return "\n".join(out)
