"""Manufacturing files of the board: Gerber (RS-274X with X2 attributes), Excellon drills, the KiCad
board and the pick-and-place list.

The bottom layer carries a ground plane: a dark region over the whole board, cleared around every
copper object of another net, then the copper itself drawn dark again (the usual Gerber way to
describe a plane without polygon clipping).
"""

from __future__ import annotations

import csv
import io
import math
import uuid
import zipfile

from . import __version__
from .font import text_strokes, text_width
from .pcb import Pcb, PlacedFootprint
from .synthesis import KIND_NAMES

MASK_EXPANSION = 0.05
SILK_WIDTH = 0.15
PLANE_CLEARANCE = 0.3
REF_HEIGHT_SMD = 0.8
REF_HEIGHT_THT = 1.0


# Silkscreen ----------------------------------------------------------------------------------------
CONNECTOR_TEXT = 0.9


def _ref_size(item: PlacedFootprint) -> float:
    return REF_HEIGHT_SMD if item.footprint.smd else REF_HEIGHT_THT


def _ref_position(item: PlacedFootprint) -> tuple[float, float]:
    """Center x and top y (absolute mm) of a part's reference, just above its courtyard."""
    cx, _ = item.center()
    _, y1, _, _ = item.courtyard()
    return cx, y1 - _ref_size(item) - 0.1


def _connector_labels(pcb: Pcb) -> list[tuple[str, float, float, str]]:
    """(text, x, center y, anchor) beside each connector pin: supply, input and output."""
    supply = f"+{pcb.board.supply_v:g}V"
    labels = []
    for ref, names in (("J1", (supply, "GND")), ("J2", ("IN", "GND")), ("J3", ("OUT", "GND"))):
        for pad, x, y, _ in pcb.footprint(ref).pads():
            label = names[int(pad.number) - 1]
            labels.append((label, x + 1.5, y, "start") if ref == "J3" else (label, x - 1.5, y, "end"))
    return labels


def silkscreen(pcb: Pcb) -> list[list[tuple[float, float]]]:
    """Every silkscreen stroke (mm, y down): outlines, references, connector labels and the title."""
    strokes: list[list[tuple[float, float]]] = []
    for item in pcb.footprints:
        for line in item.footprint.silk:
            strokes.append([(item.x + x, item.y + y) for x, y in line])
        for cx, cy, radius in item.footprint.silk_circles:
            segments = max(12, int(radius * 12))
            strokes.append(
                [(item.x + cx + radius * math.cos(2 * math.pi * k / segments), item.y + cy + radius * math.sin(2 * math.pi * k / segments)) for k in range(segments + 1)]
            )
        if item.component.symbol != "HOLE":
            size = _ref_size(item)
            cx, top = _ref_position(item)
            strokes += text_strokes(item.component.ref, cx, top, size, "middle")
    for label, x, y, anchor in _connector_labels(pcb):
        left = x if anchor == "start" else x - text_width(label, CONNECTOR_TEXT)
        strokes += text_strokes(label, left, y - CONNECTOR_TEXT / 2, CONNECTOR_TEXT)
    x1, _, x2, y2 = pcb.outline
    inputs = pcb.board.inputs
    title = f"SOFIA - {KIND_NAMES[inputs.kind]} {inputs.approximation.value} N={pcb.board.result.order} - {inputs.opamp.value}"
    strokes += text_strokes(title, (x1 + x2) / 2, y2 - 4.2, 1.3, "middle")
    return strokes


# Gerber ------------------------------------------------------------------------------------------
class _Gerber:
    def __init__(self, pcb: Pcb, function: str, polarity: str = "Positive") -> None:
        self.ox, self.oy = pcb.outline[0], pcb.outline[3]
        self.function = function
        self.polarity = polarity
        self.apertures: dict[str, int] = {}
        self.body: list[str] = ["G01*"]

    def _xy(self, x: float, y: float) -> str:
        return f"X{round((x - self.ox) * 1e6)}Y{round((self.oy - y) * 1e6)}"

    def aperture(self, kind: str, w: float, h: float | None = None) -> int:
        key = f"{kind},{w:.6f}" + ("" if h is None or kind == "C" else f"X{h:.6f}")
        if key not in self.apertures:
            self.apertures[key] = 10 + len(self.apertures)
        return self.apertures[key]

    def select(self, code: int) -> None:
        self.body.append(f"D{code}*")

    def flash(self, code: int, x: float, y: float) -> None:
        self.select(code)
        self.body.append(f"{self._xy(x, y)}D03*")

    def draw(self, code: int, points: list[tuple[float, float]]) -> None:
        if len(points) < 2:
            return
        self.select(code)
        self.body.append(f"{self._xy(*points[0])}D02*")
        self.body += [f"{self._xy(x, y)}D01*" for x, y in points[1:]]

    def region(self, points: list[tuple[float, float]]) -> None:
        self.body.append("G36*")
        self.body.append(f"{self._xy(*points[0])}D02*")
        self.body += [f"{self._xy(x, y)}D01*" for x, y in points[1:]]
        self.body.append("G37*")

    def dark(self, on: bool) -> None:
        self.body.append("%LPD*%" if on else "%LPC*%")

    def pad(self, shape: str, x: float, y: float, w: float, h: float, grow: float = 0.0) -> None:
        w, h = w + 2 * grow, h + 2 * grow
        if shape in ("rect", "roundrect"):
            code = self.aperture("R", w, h)
        elif shape == "circle" or abs(w - h) < 1e-9:
            code = self.aperture("C", min(w, h))
        else:
            code = self.aperture("O", w, h)
        self.flash(code, x, y)

    def text(self) -> str:
        head = [
            f"%TF.GenerationSoftware,SOFIA Filter Studio,{__version__}*%",
            "%TF.SameCoordinates,Original*%",
            f"%TF.FileFunction,{self.function}*%",
            f"%TF.FilePolarity,{self.polarity}*%",
            "%FSLAX46Y46*%",
            "%MOMM*%",
            "%LPD*%",
        ]
        head += [f"%ADD{code}{key}*%" for key, code in self.apertures.items()]
        return "\n".join(head + self.body + ["M02*"]) + "\n"


def _pads(pcb: Pcb):
    for item in pcb.footprints:
        for pad, x, y, net in item.pads():
            yield item, pad, x, y, net


def _copper(pcb: Pcb, layer: int) -> str:
    gerber = _Gerber(pcb, "Copper,L1,Top,Signal" if layer == 0 else "Copper,L2,Bot,Signal")
    x1, y1, x2, y2 = pcb.outline
    if layer == 1:
        inset = pcb.rules.edge
        gerber.region([(x1 + inset, y1 + inset), (x2 - inset, y1 + inset), (x2 - inset, y2 - inset), (x1 + inset, y2 - inset), (x1 + inset, y1 + inset)])
        gerber.dark(False)
        for item, pad, x, y, net in _pads(pcb):
            if not pad.plated:
                gerber.pad("circle", x, y, pad.w, pad.h, PLANE_CLEARANCE + 0.2)
            elif pad.tht and net != "GND":
                gerber.pad(pad.shape, x, y, pad.w, pad.h, PLANE_CLEARANCE)
        for track in pcb.tracks:
            if track.layer == 1 and track.net != "GND":
                gerber.draw(gerber.aperture("C", track.width + 2 * PLANE_CLEARANCE), [(track.x1, track.y1), (track.x2, track.y2)])
        for via in pcb.vias:
            if via.net != "GND":
                gerber.flash(gerber.aperture("C", via.diameter + 2 * PLANE_CLEARANCE), via.x, via.y)
        gerber.dark(True)
    for item, pad, x, y, net in _pads(pcb):
        if pad.plated and (pad.tht or layer == 0):
            gerber.pad(pad.shape, x, y, pad.w, pad.h)
    for track in pcb.tracks:
        if track.layer == layer:
            gerber.draw(gerber.aperture("C", track.width), [(track.x1, track.y1), (track.x2, track.y2)])
    for via in pcb.vias:
        gerber.flash(gerber.aperture("C", via.diameter), via.x, via.y)
    return gerber.text()


def _mask(pcb: Pcb, layer: int) -> str:
    gerber = _Gerber(pcb, "Soldermask,Top" if layer == 0 else "Soldermask,Bot", "Negative")
    for item, pad, x, y, net in _pads(pcb):
        if not pad.plated or pad.tht or layer == 0:
            gerber.pad(pad.shape, x, y, pad.w, pad.h, MASK_EXPANSION)
    return gerber.text()


def _paste(pcb: Pcb) -> str:
    gerber = _Gerber(pcb, "Paste,Top")
    for item, pad, x, y, net in _pads(pcb):
        if not pad.tht:
            gerber.pad(pad.shape, x, y, pad.w, pad.h)
    return gerber.text()


def _silk(pcb: Pcb) -> str:
    gerber = _Gerber(pcb, "Legend,Top")
    code = gerber.aperture("C", SILK_WIDTH)
    for stroke in silkscreen(pcb):
        gerber.draw(code, stroke)
    return gerber.text()


def _outline(pcb: Pcb) -> str:
    gerber = _Gerber(pcb, "Profile,NP")
    x1, y1, x2, y2 = pcb.outline
    gerber.draw(gerber.aperture("C", 0.1), [(x1, y1), (x2, y1), (x2, y2), (x1, y2), (x1, y1)])
    return gerber.text()


def _drill(pcb: Pcb, plated: bool) -> str:
    ox, oy = pcb.outline[0], pcb.outline[3]
    holes: dict[float, list[tuple[float, float]]] = {}
    for item, pad, x, y, net in _pads(pcb):
        if pad.tht and pad.plated == plated:
            holes.setdefault(round(pad.drill, 3), []).append((x, y))
    if plated:
        for via in pcb.vias:
            holes.setdefault(round(via.drill, 3), []).append((via.x, via.y))
    kind = "Plated,1,2,PTH" if plated else "NonPlated,1,2,NPTH"
    lines = ["M48", f"; DRILL file SOFIA Filter Studio {__version__}", "; FORMAT={-:-/ absolute / metric / decimal}", f"; #@! TF.FileFunction,{kind}", "FMAT,2", "METRIC"]
    tools = sorted(holes)
    lines += [f"T{index}C{size:.3f}" for index, size in enumerate(tools, start=1)]
    lines.append("%")
    for index, size in enumerate(tools, start=1):
        lines.append(f"T{index}")
        lines += [f"X{x - ox:.3f}Y{oy - y:.3f}" for x, y in holes[size]]
    lines += ["T0", "M30"]
    return "\n".join(lines) + "\n"


def gerber_files(pcb: Pcb, base: str) -> dict[str, str]:
    files = {
        f"{base}-F_Cu.gtl": _copper(pcb, 0),
        f"{base}-B_Cu.gbl": _copper(pcb, 1),
        f"{base}-F_Mask.gts": _mask(pcb, 0),
        f"{base}-B_Mask.gbs": _mask(pcb, 1),
        f"{base}-F_Silkscreen.gto": _silk(pcb),
        f"{base}-Edge_Cuts.gm1": _outline(pcb),
        f"{base}-PTH.drl": _drill(pcb, True),
        f"{base}-NPTH.drl": _drill(pcb, False),
    }
    if any(not pad.tht for _, pad, _, _, _ in _pads(pcb)):
        files[f"{base}-F_Paste.gtp"] = _paste(pcb)
    return files


def gerber_zip(pcb: Pcb, base: str) -> bytes:
    buffer = io.BytesIO()
    readme = (
        f"SOFIA Filter Studio {__version__}\n"
        f"Placa de 2 capas, {pcb.width:.1f} x {pcb.height:.1f} mm, 1.6 mm FR-4, cobre 1 oz.\n"
        f"Pista minima {pcb.rules.track} mm, separacion minima {pcb.rules.clearance} mm, via {pcb.rules.via_diameter}/{pcb.rules.via_drill} mm.\n"
        "Capas: F_Cu (arriba), B_Cu (abajo, plano de tierra), F_Mask/B_Mask, F_Silkscreen, Edge_Cuts (contorno).\n"
        "Barrenos: PTH (metalizados) y NPTH (montaje), formato Excellon metrico.\n"
    )
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in gerber_files(pcb, base).items():
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, text)
        info = zipfile.ZipInfo("LEEME.txt", date_time=(1980, 1, 1, 0, 0, 0))
        archive.writestr(info, readme)
    return buffer.getvalue()


def placement_csv(pcb: Pcb) -> str:
    """Pick-and-place list for SMD assembly (origin at the bottom-left corner, y up)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    x1, _, _, y2 = pcb.outline
    for item in pcb.footprints:
        if item.footprint.smd and item.component.in_bom:
            cx, cy = item.center()
            writer.writerow([item.component.ref, f"{cx - x1:.3f}mm", f"{y2 - cy:.3f}mm", "Top", "0"])
    return buffer.getvalue()


# KiCad board -------------------------------------------------------------------------------------
_NAMESPACE = uuid.UUID("2b7e1516-28ae-4d2a-a6d2-15b0c5e3f901")


def _q(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _f(value: float) -> str:
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("-0", "") else "0"


def to_kicad_pcb(pcb: Pcb, schematic=None) -> str:
    """KiCad 8 board (.kicad_pcb) with footprints, tracks, vias and the ground plane zone (press B in
    KiCad to fill it). Nets carry the names KiCad derives from the schematic, so both files agree."""
    from .schematic import build_schematic, kicad_net_names, kicad_unconnected_pads

    schematic = schematic or build_schematic(pcb.board)
    names = kicad_net_names(schematic)
    counter = [0]

    def uid() -> str:
        counter[0] += 1
        return str(uuid.uuid5(_NAMESPACE, f"{pcb.board.inputs}/{counter[0]}"))

    nets = pcb.nets()
    net_index = {net: index for index, net in enumerate(nets, start=1)}
    # No-connect pins get a net of their own in KiCad ("unconnected-(...)").
    unconnected = {key: (len(nets) + index, name) for index, (key, name) in enumerate(sorted(kicad_unconnected_pads(schematic).items()), start=1)}
    out = [
        "(kicad_pcb",
        "\t(version 20240108)",
        '\t(generator "sofia_filter_studio")',
        f"\t(generator_version {_q(__version__)})",
        "\t(general (thickness 1.6) (legacy_teardrops no))",
        '\t(paper "A4")',
        "\t(layers",
        '\t\t(0 "F.Cu" signal) (31 "B.Cu" signal) (34 "B.Paste" user) (35 "F.Paste" user)',
        '\t\t(36 "B.SilkS" user "B.Silkscreen") (37 "F.SilkS" user "F.Silkscreen") (38 "B.Mask" user) (39 "F.Mask" user)',
        '\t\t(44 "Edge.Cuts" user) (46 "B.CrtYd" user "B.Courtyard") (47 "F.CrtYd" user "F.Courtyard") (48 "B.Fab" user) (49 "F.Fab" user)',
        "\t)",
        "\t(setup (pad_to_mask_clearance 0.05) (allow_soldermask_bridges_in_footprints no))",
        '\t(net 0 "")',
    ]
    out += [f"\t(net {index} {_q(names.get(net, net))})" for net, index in net_index.items()]
    out += [f"\t(net {index} {_q(name)})" for index, name in unconnected.values()]
    for item in pcb.footprints:
        out += _kicad_footprint(item, net_index, names, unconnected, uid)
    x1, y1, x2, y2 = pcb.outline
    out.append(f'\t(gr_rect (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) (stroke (width 0.1) (type default)) (fill none) (layer "Edge.Cuts") (uuid {_q(uid())}))')
    inputs = pcb.board.inputs
    title = f"SOFIA - {KIND_NAMES[inputs.kind]} {inputs.approximation.value} N={pcb.board.result.order} - {inputs.opamp.value}"
    out.append(
        f'\t(gr_text {_q(title)} (at {_f((x1 + x2) / 2)} {_f(y2 - 3.5)} 0) (layer "F.SilkS") (uuid {_q(uid())}) '
        "(effects (font (size 1.3 1.3) (thickness 0.18))))"
    )
    for label, x, y, anchor in _connector_labels(pcb):
        justify = "left" if anchor == "start" else "right"
        out.append(
            f'\t(gr_text {_q(label)} (at {_f(x)} {_f(y)} 0) (layer "F.SilkS") (uuid {_q(uid())}) '
            f"(effects (font (size {_f(CONNECTOR_TEXT)} {_f(CONNECTOR_TEXT)}) (thickness {_f(SILK_WIDTH)})) (justify {justify})))"
        )
    for track in pcb.tracks:
        layer = "F.Cu" if track.layer == 0 else "B.Cu"
        out.append(
            f"\t(segment (start {_f(track.x1)} {_f(track.y1)}) (end {_f(track.x2)} {_f(track.y2)}) (width {_f(track.width)}) "
            f'(layer "{layer}") (net {net_index[track.net]}) (uuid {_q(uid())}))'
        )
    for via in pcb.vias:
        out.append(
            f'\t(via (at {_f(via.x)} {_f(via.y)}) (size {_f(via.diameter)}) (drill {_f(via.drill)}) (layers "F.Cu" "B.Cu") '
            f"(net {net_index[via.net]}) (uuid {_q(uid())}))"
        )
    if "GND" in net_index:
        inset = pcb.rules.edge
        points = " ".join(f"(xy {_f(x)} {_f(y)})" for x, y in ((x1 + inset, y1 + inset), (x2 - inset, y1 + inset), (x2 - inset, y2 - inset), (x1 + inset, y2 - inset)))
        out.append(
            f'\t(zone (net {net_index["GND"]}) (net_name "GND") (layer "B.Cu") (uuid {_q(uid())}) (hatch edge 0.5) '
            f"(connect_pads (clearance {_f(PLANE_CLEARANCE)})) (min_thickness 0.25) (filled_areas_thickness no) "
            f"(fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {points})))"
        )
    out.append(")")
    return "\n".join(out) + "\n"


def _kicad_footprint(
    item: PlacedFootprint, net_index: dict[str, int], names: dict[str, str], unconnected: dict[tuple[str, str], tuple[int, str]], uid
) -> list[str]:
    component, footprint = item.component, item.footprint
    smd = footprint.smd
    x1, y1, x2, y2 = footprint.courtyard
    cx = (x1 + x2) / 2
    size = _ref_size(item)
    ref_x, ref_top = _ref_position(item)
    ref_font = f"(font (size {_f(size)} {_f(size)}) (thickness {_f(SILK_WIDTH)}))"
    lines = [
        f'\t(footprint {_q(footprint.name)} (layer "F.Cu") (uuid {_q(uid())}) (at {_f(item.x)} {_f(item.y)})',
        f'\t\t(property "Reference" {_q(component.ref)} (at {_f(ref_x - item.x)} {_f(ref_top + size / 2 - item.y)} 0) (layer "F.SilkS") (uuid {_q(uid())}) (effects {ref_font}))',
        f'\t\t(property "Value" {_q(component.value)} (at {_f(cx)} {_f(y2 + 0.8)} 0) (layer "F.Fab") (uuid {_q(uid())}) (effects (font (size 1 1) (thickness 0.15))))',
        f'\t\t(property "Footprint" {_q(footprint.name)} (at 0 0 0) (layer "F.Fab") (hide yes) (uuid {_q(uid())}) (effects (font (size 1 1) (thickness 0.15))))',
        f"\t\t(attr {'smd' if smd else 'through_hole'}{'' if component.in_bom else ' exclude_from_bom'})",
    ]
    if component.description:
        lines.insert(
            4, f'\t\t(property "Description" {_q(component.description)} (at 0 0 0) (layer "F.Fab") (hide yes) (uuid {_q(uid())}) (effects (font (size 1 1) (thickness 0.15))))'
        )
    for line in footprint.silk:
        for (ax, ay), (bx, by) in zip(line, line[1:]):
            lines.append(f'\t\t(fp_line (start {_f(ax)} {_f(ay)}) (end {_f(bx)} {_f(by)}) (stroke (width 0.12) (type solid)) (layer "F.SilkS") (uuid {_q(uid())}))')
    for ccx, ccy, radius in footprint.silk_circles:
        lines.append(f'\t\t(fp_circle (center {_f(ccx)} {_f(ccy)}) (end {_f(ccx + radius)} {_f(ccy)}) (stroke (width 0.12) (type solid)) (fill none) (layer "F.SilkS") (uuid {_q(uid())}))')
    lines.append(f'\t\t(fp_rect (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) (stroke (width 0.05) (type solid)) (fill none) (layer "F.CrtYd") (uuid {_q(uid())}))')
    for pad in footprint.pads:
        net = component.pins.get(pad.number, "")
        if net:
            net_text = f" (net {net_index[net]} {_q(names.get(net, net))})"
        elif (component.ref, pad.number) in unconnected:
            index, name = unconnected[(component.ref, pad.number)]
            net_text = f" (net {index} {_q(name)})"
        else:
            net_text = ""
        if not pad.plated:
            lines.append(f'\t\t(pad "" np_thru_hole circle (at {_f(pad.x)} {_f(pad.y)}) (size {_f(pad.w)} {_f(pad.h)}) (drill {_f(pad.drill)}) (layers "*.Cu" "*.Mask") (uuid {_q(uid())}))')
        elif pad.tht:
            lines.append(
                f'\t\t(pad {_q(pad.number)} thru_hole {pad.shape} (at {_f(pad.x)} {_f(pad.y)}) (size {_f(pad.w)} {_f(pad.h)}) (drill {_f(pad.drill)}) '
                f'(layers "*.Cu" "*.Mask"){net_text} (uuid {_q(uid())}))'
            )
        else:
            ratio = f" (roundrect_rratio {pad.rratio:g})" if pad.shape == "roundrect" else ""
            lines.append(
                f'\t\t(pad {_q(pad.number)} smd {pad.shape} (at {_f(pad.x)} {_f(pad.y)}) (size {_f(pad.w)} {_f(pad.h)}) '
                f'(layers "F.Cu" "F.Paste" "F.Mask"){ratio}{net_text} (uuid {_q(uid())}))'
            )
    lines.append("\t)")
    return lines
