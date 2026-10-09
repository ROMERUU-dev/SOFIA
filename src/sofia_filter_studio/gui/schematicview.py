"""Schematic viewer: the SVG in a QGraphicsView with wheel zoom, drag to pan and double click to fit."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QGraphicsSvgItem
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView

from . import theme


class SchematicView(QGraphicsView):
    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QColor(theme.SURFACE))
        self.setMinimumHeight(220)
        self.setToolTip("Rueda: zoom · arrastrar: mover · doble clic: ajustar")
        self._renderer: QSvgRenderer | None = None
        self._item: QGraphicsSvgItem | None = None
        self._user_zoomed = False

    def show_svg(self, markup: str) -> None:
        self.scene().clear()
        self._renderer = QSvgRenderer(markup.encode("utf-8"), self)
        self._item = QGraphicsSvgItem()
        self._item.setSharedRenderer(self._renderer)
        # Re-render the vectors at every zoom level instead of scaling a cached bitmap.
        self._item.setCacheMode(QGraphicsSvgItem.CacheMode.NoCache)
        self.scene().addItem(self._item)
        self.scene().setSceneRect(self._item.boundingRect())
        self._user_zoomed = False
        self.fit()

    def show_message(self, text: str) -> None:
        self.scene().clear()
        self._item = None
        item = self.scene().addText(text)
        item.setDefaultTextColor(QColor(theme.MUTED))
        self.scene().setSceneRect(item.boundingRect())
        self.resetTransform()

    def fit(self) -> None:
        if self._item is not None:
            self.resetTransform()
            self.fitInView(self._item, Qt.AspectRatioMode.KeepAspectRatio)
            self._user_zoomed = False

    def wheelEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._item is None:
            return
        factor = 1.15 ** (event.angleDelta().y() / 120)
        self.scale(factor, factor)
        self._user_zoomed = True

    def mouseDoubleClickEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.fit()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        super().resizeEvent(event)
        if not self._user_zoomed:
            self.fit()
