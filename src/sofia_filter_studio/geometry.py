"""Copper shapes and exact distances between them (for the router and the design-rule check)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Capsule:
    """A segment with a radius: tracks, round and oval pads, vias (zero-length segment)."""

    ax: float
    ay: float
    bx: float
    by: float
    r: float

    def bounds(self) -> tuple[float, float, float, float]:
        return min(self.ax, self.bx) - self.r, min(self.ay, self.by) - self.r, max(self.ax, self.bx) + self.r, max(self.ay, self.by) + self.r


@dataclass(frozen=True, slots=True)
class Box:
    """An axis-aligned rectangle: rectangular pads (rounded corners are treated as square)."""

    x1: float
    y1: float
    x2: float
    y2: float

    def bounds(self) -> tuple[float, float, float, float]:
        return self.x1, self.y1, self.x2, self.y2


Shape = Capsule | Box


def circle(x: float, y: float, r: float) -> Capsule:
    return Capsule(x, y, x, y, r)


def pad_shape(shape: str, x: float, y: float, w: float, h: float) -> Shape:
    if shape in ("rect", "roundrect"):
        return Box(x - w / 2, y - h / 2, x + w / 2, y + h / 2)
    if shape == "circle" or abs(w - h) < 1e-9:
        return circle(x, y, min(w, h) / 2)
    if w > h:
        return Capsule(x - (w - h) / 2, y, x + (w - h) / 2, y, h / 2)
    return Capsule(x, y - (h - w) / 2, x, y + (h - w) / 2, w / 2)


def _point_segment(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = bx - ax, by - ay
    length = dx * dx + dy * dy
    t = 0.0 if length == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _segments_intersect(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> bool:
    def orient(px, py, qx, qy, rx, ry):
        value = (qx - px) * (ry - py) - (qy - py) * (rx - px)
        return 0 if abs(value) < 1e-12 else (1 if value > 0 else -1)

    ax, ay, bx, by = a
    cx, cy, dx, dy = b
    o1, o2 = orient(ax, ay, bx, by, cx, cy), orient(ax, ay, bx, by, dx, dy)
    o3, o4 = orient(cx, cy, dx, dy, ax, ay), orient(cx, cy, dx, dy, bx, by)
    return o1 != o2 and o3 != o4 and 0 not in (o1, o2, o3, o4)


def _segment_segment(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    if _segments_intersect(a, b):
        return 0.0
    ax, ay, bx, by = a
    cx, cy, dx, dy = b
    return min(
        _point_segment(ax, ay, cx, cy, dx, dy),
        _point_segment(bx, by, cx, cy, dx, dy),
        _point_segment(cx, cy, ax, ay, bx, by),
        _point_segment(dx, dy, ax, ay, bx, by),
    )


def _point_box(px: float, py: float, box: Box) -> float:
    dx = max(box.x1 - px, 0.0, px - box.x2)
    dy = max(box.y1 - py, 0.0, py - box.y2)
    return math.hypot(dx, dy)


def _segment_box(ax: float, ay: float, bx: float, by: float, box: Box) -> float:
    if box.x1 <= ax <= box.x2 and box.y1 <= ay <= box.y2:
        return 0.0
    edges = (
        (box.x1, box.y1, box.x2, box.y1),
        (box.x2, box.y1, box.x2, box.y2),
        (box.x2, box.y2, box.x1, box.y2),
        (box.x1, box.y2, box.x1, box.y1),
    )
    return min(_segment_segment((ax, ay, bx, by), edge) for edge in edges)


def distance(a: Shape, b: Shape) -> float:
    """Gap between two copper shapes (0 when they touch or overlap)."""
    if isinstance(a, Capsule) and a.ax == a.bx and a.ay == a.by:
        return max(point_distance(a.ax, a.ay, b) - a.r, 0.0)
    if isinstance(b, Capsule) and b.ax == b.bx and b.ay == b.by:
        return max(point_distance(b.ax, b.ay, a) - b.r, 0.0)
    if isinstance(a, Capsule) and isinstance(b, Capsule):
        gap = _segment_segment((a.ax, a.ay, a.bx, a.by), (b.ax, b.ay, b.bx, b.by)) - a.r - b.r
    elif isinstance(a, Capsule):
        gap = _segment_box(a.ax, a.ay, a.bx, a.by, b) - a.r
    elif isinstance(b, Capsule):
        gap = _segment_box(b.ax, b.ay, b.bx, b.by, a) - b.r
    else:
        dx = max(a.x1 - b.x2, 0.0, b.x1 - a.x2)
        dy = max(a.y1 - b.y2, 0.0, b.y1 - a.y2)
        gap = math.hypot(dx, dy)
    return max(gap, 0.0)


def point_distance(px: float, py: float, shape: Shape) -> float:
    if isinstance(shape, Capsule):
        return max(_point_segment(px, py, shape.ax, shape.ay, shape.bx, shape.by) - shape.r, 0.0)
    return _point_box(px, py, shape)
