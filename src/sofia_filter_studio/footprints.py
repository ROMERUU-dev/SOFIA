"""Footprints used on the board, with the KiCad library names and their pad geometry.

Coordinates are millimetres relative to the KiCad footprint origin (y down). Dimensions follow the
KiCad standard libraries, so a board opened in KiCad matches its library footprints. Footprints are
always placed unrotated; that keeps every tool's rotation conventions out of the way.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Pad:
    number: str
    shape: str  # rect, roundrect, circle, oval
    x: float
    y: float
    w: float
    h: float
    drill: float | None = None  # None: SMD pad on the top layer
    plated: bool = True
    rratio: float = 0.25  # corner radius / smaller side, for roundrect pads

    @property
    def tht(self) -> bool:
        return self.drill is not None


@dataclass(frozen=True, slots=True)
class Footprint:
    name: str
    pads: tuple[Pad, ...]
    courtyard: tuple[float, float, float, float]  # x1, y1, x2, y2
    silk: tuple[tuple[tuple[float, float], ...], ...] = field(default_factory=tuple)  # polylines
    silk_circles: tuple[tuple[float, float, float], ...] = field(default_factory=tuple)

    @property
    def smd(self) -> bool:
        return all(not pad.tht for pad in self.pads)

    def center(self) -> tuple[float, float]:
        x1, y1, x2, y2 = self.courtyard
        return (x1 + x2) / 2, (y1 + y2) / 2


def _two_smd(name: str, w: float, h: float, x: float, courtyard: tuple[float, float], silk_y: float, rratio: float) -> Footprint:
    cx, cy = courtyard
    silk = (((-0.25, -silk_y), (0.25, -silk_y)), ((-0.25, silk_y), (0.25, silk_y))) if silk_y else ()
    pads = (Pad("1", "roundrect", -x, 0, w, h, rratio=rratio), Pad("2", "roundrect", x, 0, w, h, rratio=rratio))
    return Footprint(name, pads, (-cx, -cy, cx, cy), silk)


def _soic(name: str, pins: int, body: float) -> Footprint:
    per_side = pins // 2
    pitch = 1.27
    top = -(per_side - 1) * pitch / 2
    pads = []
    for index in range(per_side):
        pads.append(Pad(str(index + 1), "roundrect", -2.475, top + index * pitch, 1.95, 0.6))
    for index in range(per_side):
        pads.append(Pad(str(per_side + index + 1), "roundrect", 2.475, -top - index * pitch, 1.95, 0.6))
    half = body / 2 + 0.11
    edge = round(body / 2 + 0.25, 2)
    top_line = ((-1.95, -half), (1.95, -half))
    bottom_line = ((-1.95, half), (1.95, half))
    return Footprint(name, tuple(pads), (-3.7, -edge, 3.7, edge), (top_line, bottom_line), silk_circles=((-3.25, -half - 0.05, 0.15),))


def _dip(name: str, pins: int, courtyard: tuple[float, float, float, float]) -> Footprint:
    per_side = pins // 2
    pads = []
    for index in range(per_side):
        pads.append(Pad(str(index + 1), "roundrect" if index == 0 else "circle", 0, index * 2.54, 1.6, 1.6, 0.8, rratio=0.15625))
    for index in range(per_side):
        pads.append(Pad(str(per_side + index + 1), "circle", 7.62, (per_side - 1 - index) * 2.54, 1.6, 1.6, 0.8))
    bottom = (per_side - 1) * 2.54
    outline = ((2.8, -1.33), (1.16, -1.33), (1.16, bottom + 1.33), (6.46, bottom + 1.33), (6.46, -1.33), (4.82, -1.33))
    return Footprint(name, tuple(pads), courtyard, (outline,))


FOOTPRINTS: dict[str, Footprint] = {}


def _add(footprint: Footprint) -> None:
    FOOTPRINTS[footprint.name] = footprint


_add(_two_smd("Resistor_SMD:R_0805_2012Metric", 1.025, 1.4, 0.9125, (1.68, 0.95), 0.735, 0.243902))
_add(_two_smd("Capacitor_SMD:C_0805_2012Metric", 1.0, 1.45, 0.95, (1.7, 0.98), 0.735, 0.25))
_add(_two_smd("Capacitor_SMD:C_1206_3216Metric", 1.15, 1.8, 1.475, (2.3, 1.15), 0.91, 0.217391))
_add(_two_smd("Capacitor_SMD:C_1812_4532Metric", 1.4, 3.4, 2.05, (3.0, 1.95), 1.71, 0.178571))
_add(
    Footprint(
        "Capacitor_SMD:CP_Elec_6.3x5.4",
        (Pad("1", "roundrect", -2.8, 0, 3.5, 1.6, rratio=0.15625), Pad("2", "roundrect", 2.8, 0, 3.5, 1.6, rratio=0.15625)),
        (-4.8, -3.55, 4.8, 3.55),
        (((-3.4, -1.06), (-3.4, -2.2), (-2.2, -3.4), (3.4, -3.4), (3.4, -1.06)), ((-3.4, 1.06), (-3.4, 2.2), (-2.2, 3.4), (3.4, 3.4), (3.4, 1.06)), ((-4.4, -1.6), (-4.4, -2.6))),
    )
)
_add(_soic("Package_SO:SOIC-8_3.9x4.9mm_P1.27mm", 8, 4.9))
_add(_soic("Package_SO:SOIC-14_3.9x8.7mm_P1.27mm", 14, 8.65))
_add(_dip("Package_DIP:DIP-8_W7.62mm", 8, (-1.06, -1.52, 8.67, 9.14)))
_add(_dip("Package_DIP:DIP-14_W7.62mm", 14, (-1.06, -1.53, 8.67, 16.77)))
_add(
    Footprint(
        "Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal",
        (Pad("1", "circle", 0, 0, 1.6, 1.6, 0.8), Pad("2", "circle", 10.16, 0, 1.6, 1.6, 0.8)),
        (-1.05, -1.5, 11.21, 1.5),
        (((1.81, -1.37), (8.35, -1.37), (8.35, 1.37), (1.81, 1.37), (1.81, -1.37)), ((1.04, 0), (1.81, 0)), ((9.12, 0), (8.35, 0))),
    )
)
_add(
    Footprint(
        "Capacitor_THT:C_Rect_L7.2mm_W3.5mm_P5.00mm_FKS2_FKP2_MKS2_MKP2",
        (Pad("1", "circle", 0, 0, 1.6, 1.6, 0.8), Pad("2", "circle", 5.0, 0, 1.6, 1.6, 0.8)),
        (-1.35, -2.0, 6.35, 2.0),
        (((-1.22, -1.87), (6.22, -1.87), (6.22, 1.87), (-1.22, 1.87), (-1.22, -1.87)),),
    )
)
_add(
    Footprint(
        "Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm",
        (Pad("1", "circle", 0, 0, 1.6, 1.6, 0.8), Pad("2", "circle", 5.0, 0, 1.6, 1.6, 0.8)),
        (-1.05, -1.5, 6.05, 1.5),
        (((0.95, -1.37), (4.05, -1.37)), ((0.95, 1.37), (4.05, 1.37))),
    )
)
_add(
    Footprint(
        "Capacitor_THT:CP_Radial_D5.0mm_P2.00mm",
        (Pad("1", "roundrect", 0, 0, 1.6, 1.6, 0.8, rratio=0.15625), Pad("2", "circle", 2.0, 0, 1.6, 1.6, 0.8)),
        (-1.75, -2.75, 3.75, 2.75),
        (((-1.55, -1.9), (-0.55, -1.9)), ((-1.05, -2.4), (-1.05, -1.4))),
        silk_circles=((1.0, 0, 2.62),),
    )
)
_add(
    Footprint(
        "Capacitor_THT:CP_Radial_D6.3mm_P2.50mm",
        (Pad("1", "roundrect", 0, 0, 1.6, 1.6, 0.8, rratio=0.15625), Pad("2", "circle", 2.5, 0, 1.6, 1.6, 0.8)),
        (-2.15, -3.4, 4.65, 3.4),
        (((-1.9, -2.3), (-0.9, -2.3)), ((-1.4, -2.8), (-1.4, -1.8))),
        silk_circles=((1.25, 0, 3.27),),
    )
)
_add(
    Footprint(
        "Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
        (Pad("1", "rect", 0, 0, 1.7, 1.7, 1.0), Pad("2", "circle", 0, 2.54, 1.7, 1.7, 1.0)),
        (-1.77, -1.77, 1.77, 4.32),
        (((-1.33, 1.27), (-1.33, 3.87), (1.33, 3.87), (1.33, 1.27), (-1.33, 1.27)), ((-1.33, 0), (-1.33, -1.33), (0, -1.33))),
    )
)
_add(
    Footprint(
        "MountingHole:MountingHole_3.2mm_M3",
        (Pad("", "circle", 0, 0, 3.2, 3.2, 3.2, plated=False),),
        (-3.45, -3.45, 3.45, 3.45),
        silk_circles=((0, 0, 3.2),),
    )
)
