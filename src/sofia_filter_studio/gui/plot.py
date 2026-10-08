"""Frequency-response plot painted with QPainter: log axis, spec mask, zoom/pan and hover readout."""

from __future__ import annotations

import math
from bisect import bisect_left

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QSizePolicy, QWidget

from ..units import format_quantity
from . import theme

# Deepest level the automatic view goes to; ideal notches reach -inf, so they are cut here.
AUTO_FLOOR_DB = -240.0
WHEEL_STEP = 0.85


class ResponsePlot(QWidget):
    """Mouse wheel zooms around the cursor (Shift: only dB, Ctrl: only frequency), dragging pans and a
    double click returns to the full view."""

    MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM = 62, 18, 14, 34

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self._freqs: list[float] = []
        self._gains: list[float] = []
        self._passbands: list[tuple[float, float]] = []
        self._stopbands: list[tuple[float, float]] = []
        self._ripple_db = 1.0
        self._attenuation_db = 40.0
        self._hover_x: float | None = None
        self._passband_view = False
        # View window: log10(frequency) range and dB range (top > bottom).
        self._x_lo = self._x_hi = 0.0
        self._y_top, self._y_bottom = 5.0, -60.0
        self._drag_origin: QPointF | None = None
        self._drag_view: tuple[float, float, float, float] | None = None

    # Data and views -------------------------------------------------------------------------------
    def set_data(
        self,
        freqs: list[float],
        gains: list[float],
        passbands: list[tuple[float, float]],
        stopbands: list[tuple[float, float]],
        ripple_db: float,
        attenuation_db: float,
    ) -> None:
        self._freqs, self._gains = freqs, gains
        self._passbands, self._stopbands = passbands, stopbands
        self._ripple_db, self._attenuation_db = ripple_db, attenuation_db
        self.reset_view()

    def clear(self) -> None:
        self._freqs, self._gains = [], []
        self.update()

    def set_passband_view(self, enabled: bool) -> None:
        """Zoom the vertical axis on the passband so the ripple is readable."""
        self._passband_view = enabled
        self.reset_view()

    def reset_view(self) -> None:
        if not self._freqs:
            self.update()
            return
        self._x_lo, self._x_hi = math.log10(self._freqs[0]), math.log10(self._freqs[-1])
        if self._passband_view:
            span = max(0.5, self._ripple_db)
            self._y_top, self._y_bottom = span * 0.5, -span * 2.5
        else:
            # Whole curve: down to its deepest point (at least As + 20 dB below 0 dB).
            finite = [gain for gain in self._gains if gain > AUTO_FLOOR_DB]
            deepest = min(finite) if finite else AUTO_FLOOR_DB
            floor_for_spec = -math.ceil((self._attenuation_db + 20) / 20) * 20
            self._y_top = 5.0
            self._y_bottom = float(max(min(math.floor((deepest - 5) / 20) * 20, floor_for_spec), AUTO_FLOOR_DB))
        self.update()

    # Geometry -------------------------------------------------------------------------------------
    def _plot_rect(self) -> QRectF:
        return QRectF(
            self.MARGIN_LEFT,
            self.MARGIN_TOP,
            max(10, self.width() - self.MARGIN_LEFT - self.MARGIN_RIGHT),
            max(10, self.height() - self.MARGIN_TOP - self.MARGIN_BOTTOM),
        )

    def _x(self, freq: float, rect: QRectF) -> float:
        return rect.left() + (math.log10(freq) - self._x_lo) / (self._x_hi - self._x_lo) * rect.width()

    def _y(self, gain: float, rect: QRectF) -> float:
        span = self._y_top - self._y_bottom
        # Keep coordinates bounded; the painter clips anything outside the plot.
        gain = min(self._y_top + span, max(self._y_bottom - span, gain))
        return rect.top() + (self._y_top - gain) / span * rect.height()

    def _y_step(self) -> float:
        span = self._y_top - self._y_bottom
        for step in (0.01, 0.02, 0.05, 0.1, 0.2, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 50):
            if span / step <= 9:
                return step
        return 100.0

    # Mouse ----------------------------------------------------------------------------------------
    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if not self._freqs:
            return
        rect = self._plot_rect()
        position = event.position()
        factor = WHEEL_STEP ** (event.angleDelta().y() / 120)
        modifiers = event.modifiers()
        if not modifiers & Qt.KeyboardModifier.ShiftModifier:
            anchor = self._x_lo + (position.x() - rect.left()) / rect.width() * (self._x_hi - self._x_lo)
            lo = anchor - (anchor - self._x_lo) * factor
            hi = anchor + (self._x_hi - anchor) * factor
            data_lo, data_hi = math.log10(self._freqs[0]), math.log10(self._freqs[-1])
            if hi - lo >= 0.02:
                self._x_lo, self._x_hi = max(lo, data_lo), min(hi, data_hi)
        if not modifiers & Qt.KeyboardModifier.ControlModifier:
            anchor = self._y_top - (position.y() - rect.top()) / rect.height() * (self._y_top - self._y_bottom)
            top = anchor + (self._y_top - anchor) * factor
            bottom = anchor - (anchor - self._y_bottom) * factor
            if top - bottom >= 0.05:
                self._y_top, self._y_bottom = min(top, 40.0), max(bottom, -400.0)
        event.accept()
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if event.button() == Qt.MouseButton.LeftButton and self._freqs:
            self._drag_origin = event.position()
            self._drag_view = (self._x_lo, self._x_hi, self._y_top, self._y_bottom)
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._drag_origin = None
        self.setCursor(Qt.CursorShape.CrossCursor)

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.reset_view()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        rect = self._plot_rect()
        position = event.position()
        if self._drag_origin is not None and self._drag_view is not None:
            x_lo, x_hi, y_top, y_bottom = self._drag_view
            dx = (position.x() - self._drag_origin.x()) / rect.width() * (x_hi - x_lo)
            dy = (position.y() - self._drag_origin.y()) / rect.height() * (y_top - y_bottom)
            data_lo, data_hi = math.log10(self._freqs[0]), math.log10(self._freqs[-1])
            dx = min(max(dx, x_hi - data_hi), x_lo - data_lo)
            self._x_lo, self._x_hi = x_lo - dx, x_hi - dx
            self._y_top, self._y_bottom = y_top + dy, y_bottom + dy
        self._hover_x = position.x() if rect.left() <= position.x() <= rect.right() else None
        self.update()

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self._hover_x = None
        self.update()

    # Painting -------------------------------------------------------------------------------------
    def paintEvent(self, event) -> None:  # noqa: N802 (Qt API)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self._plot_rect()
        painter.fillRect(rect, QColor(theme.SURFACE))
        if len(self._freqs) < 2:
            painter.setPen(QColor(theme.MUTED))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Completa la especificación para ver la respuesta")
            return
        painter.save()
        painter.setClipRect(rect)
        self._paint_mask(painter, rect)
        painter.restore()
        self._paint_grid(painter, rect)
        self._paint_curve(painter, rect)
        self._paint_hover(painter, rect)

    def _paint_mask(self, painter: QPainter, rect: QRectF) -> None:
        forbidden = QColor(theme.FORBIDDEN)
        forbidden.setAlpha(26)
        edge = QColor(theme.FORBIDDEN)
        edge.setAlpha(140)
        pen = QPen(edge, 1.2, Qt.PenStyle.DashLine)
        f_lo, f_hi = self._freqs[0], self._freqs[-1]
        for lo, hi in self._passbands:
            lo, hi = max(lo, f_lo), min(hi, f_hi)
            if hi <= lo:
                continue
            x0, x1 = self._x(lo, rect), self._x(hi, rect)
            y = self._y(-self._ripple_db, rect)
            painter.fillRect(QRectF(x0, y, x1 - x0, rect.bottom() - y), forbidden)
            painter.setPen(pen)
            painter.drawLine(QPointF(x0, y), QPointF(x1, y))
        for lo, hi in self._stopbands:
            lo, hi = max(lo, f_lo), min(hi, f_hi)
            if hi <= lo:
                continue
            x0, x1 = self._x(lo, rect), self._x(hi, rect)
            y = self._y(-self._attenuation_db, rect)
            painter.fillRect(QRectF(x0, rect.top(), x1 - x0, y - rect.top()), forbidden)
            painter.setPen(pen)
            painter.drawLine(QPointF(x0, y), QPointF(x1, y))

    def _paint_grid(self, painter: QPainter, rect: QRectF) -> None:
        small = QFont(self.font())
        small.setPointSizeF(max(7.5, self.font().pointSizeF() - 1.5))
        painter.setFont(small)
        # Label the 2-3-5-7 ticks whenever they fit (always when zoomed in), so the axis keeps a scale.
        # 5 -> 7 is the closest pair of labels on a log axis.
        pixels_per_decade = rect.width() / (self._x_hi - self._x_lo)
        label_minor = pixels_per_decade * math.log10(7 / 5) >= painter.fontMetrics().horizontalAdvance("700 Hz") + 10
        for decade in range(math.floor(self._x_lo), math.ceil(self._x_hi) + 1):
            for step in range(1, 10):
                freq = step * 10**decade
                position = math.log10(freq)
                if not self._x_lo <= position <= self._x_hi:
                    continue
                x = self._x(freq, rect)
                painter.setPen(QPen(QColor(theme.GRID_STRONG if step == 1 else theme.GRID), 1))
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
                if step == 1 or (label_minor and step in (2, 3, 5, 7)):
                    painter.setPen(QColor(theme.MUTED))
                    # Keep edge labels inside the widget instead of cutting them.
                    label_x = min(max(x - 40, 0.0), self.width() - 80.0)
                    painter.drawText(
                        QRectF(label_x, rect.bottom() + 6, 80, 18),
                        Qt.AlignmentFlag.AlignHCenter,
                        format_quantity(freq, "Hz", 3),
                    )
        step_db = self._y_step()
        decimals = 0 if step_db >= 1 else (1 if step_db >= 0.1 else 2)
        gain = math.floor(self._y_top / step_db) * step_db
        while gain >= self._y_bottom - 1e-9:
            y = self._y(gain, rect)
            painter.setPen(QPen(QColor(theme.GRID_STRONG if abs(gain) < 1e-9 else theme.GRID), 1))
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
            painter.setPen(QColor(theme.MUTED))
            label = f"{gain + 0.0:.{decimals}f} dB"
            painter.drawText(QRectF(0, y - 9, rect.left() - 8, 18), Qt.AlignmentFlag.AlignRight, label)
            gain -= step_db
        painter.setPen(QPen(QColor(theme.BORDER), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)

    def _paint_curve(self, painter: QPainter, rect: QRectF) -> None:
        path = QPainterPath()
        for index, (freq, gain) in enumerate(zip(self._freqs, self._gains)):
            point = QPointF(self._x(freq, rect), self._y(gain, rect))
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)
        painter.save()
        painter.setClipRect(rect)
        pen = QPen(QColor(theme.ACCENT), 2.4)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.drawPath(path)
        painter.restore()

    def _paint_hover(self, painter: QPainter, rect: QRectF) -> None:
        if self._hover_x is None or self._drag_origin is not None:
            return
        position = self._x_lo + (self._hover_x - rect.left()) / rect.width() * (self._x_hi - self._x_lo)
        index = min(len(self._freqs) - 1, bisect_left(self._freqs, 10**position))
        freq, gain = self._freqs[index], self._gains[index]
        x, y = self._x(freq, rect), self._y(gain, rect)
        painter.setPen(QPen(QColor(theme.MUTED), 1, Qt.PenStyle.DotLine))
        painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
        if rect.top() <= y <= rect.bottom():
            painter.setPen(QPen(QColor(theme.SURFACE), 2))
            painter.setBrush(QBrush(QColor(theme.ACCENT)))
            painter.drawEllipse(QPointF(x, y), 4.5, 4.5)
        label = f"{format_quantity(freq, 'Hz', 4)}   {gain:.2f} dB"
        metrics = painter.fontMetrics()
        width, height = metrics.horizontalAdvance(label) + 16, metrics.height() + 10
        box_x = x + 10 if x + 10 + width < rect.right() else x - 10 - width
        box = QRectF(box_x, rect.top() + 8, width, height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(theme.TEXT))
        painter.drawRoundedRect(box, 6, 6)
        painter.setPen(QColor("white"))
        painter.drawText(box, Qt.AlignmentFlag.AlignCenter, label)
