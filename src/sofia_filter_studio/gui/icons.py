"""Small response-shape icons drawn with QPainter (no image files)."""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ..models import FilterKind
from . import theme

SCALE = 3


def _shape(kind: FilterKind, rect: QRectF) -> QPainterPath:
    left, right, top, bottom = rect.left(), rect.right(), rect.top() + 2, rect.bottom()
    width = right - left
    path = QPainterPath()
    if kind is FilterKind.LOWPASS:
        path.moveTo(left, top)
        path.lineTo(left + width * 0.42, top)
        path.cubicTo(left + width * 0.58, top, left + width * 0.62, bottom, left + width * 0.82, bottom)
        path.lineTo(right, bottom)
    elif kind is FilterKind.HIGHPASS:
        path.moveTo(left, bottom)
        path.lineTo(left + width * 0.18, bottom)
        path.cubicTo(left + width * 0.38, bottom, left + width * 0.42, top, left + width * 0.58, top)
        path.lineTo(right, top)
    elif kind is FilterKind.BANDPASS:
        path.moveTo(left, bottom)
        path.lineTo(left + width * 0.12, bottom)
        path.cubicTo(left + width * 0.3, bottom, left + width * 0.32, top, left + width * 0.42, top)
        path.lineTo(left + width * 0.58, top)
        path.cubicTo(left + width * 0.68, top, left + width * 0.7, bottom, left + width * 0.88, bottom)
        path.lineTo(right, bottom)
    else:
        path.moveTo(left, top)
        path.lineTo(left + width * 0.3, top)
        path.cubicTo(left + width * 0.42, top, left + width * 0.44, bottom, left + width * 0.5, bottom)
        path.cubicTo(left + width * 0.56, bottom, left + width * 0.58, top, left + width * 0.7, top)
        path.lineTo(right, top)
    return path


def _pixmap(kind: FilterKind, color: str, width: int, height: int) -> QPixmap:
    pixmap = QPixmap(width * SCALE, height * SCALE)
    pixmap.setDevicePixelRatio(SCALE)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(theme.GRID_STRONG), 1.2))
    painter.drawLine(QPointF(3, height - 3), QPointF(width - 2, height - 3))
    painter.drawLine(QPointF(3, 3), QPointF(3, height - 3))
    pen = QPen(QColor(color), 2.4)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.drawPath(_shape(kind, QRectF(7, 5, width - 11, height - 11)))
    painter.end()
    return pixmap


def response_icon(kind: FilterKind, size: tuple[int, int] = (64, 36)) -> QIcon:
    """Muted curve when unchecked, accent curve when checked."""
    width, height = size
    icon = QIcon()
    icon.addPixmap(_pixmap(kind, theme.MUTED, width, height), QIcon.Mode.Normal, QIcon.State.Off)
    icon.addPixmap(_pixmap(kind, theme.ACCENT, width, height), QIcon.Mode.Normal, QIcon.State.On)
    return icon


def combo_arrow_file() -> str:
    """Chevron PNG for QComboBox::down-arrow (style sheets only take image files)."""
    path = Path(tempfile.gettempdir()) / "sofia_filter_studio_chevron.png"
    if not path.exists():
        pixmap = QPixmap(30, 18)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(QColor(theme.MUTED), 3.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPolyline([QPointF(4, 4), QPointF(15, 14), QPointF(26, 4)])
        painter.end()
        pixmap.save(str(path), "PNG")
    return path.as_posix()


def app_icon() -> QIcon:
    icon = QIcon()
    for size in (16, 32, 48, 64, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.ACCENT))
        painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
        pen = QPen(QColor("white"), max(1.5, size * 0.07))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        margin = size * 0.18
        painter.drawPath(_shape(FilterKind.BANDPASS, QRectF(margin, margin * 1.4, size - 2 * margin, size - 2.6 * margin)))
        painter.end()
        icon.addPixmap(pixmap)
    return icon
