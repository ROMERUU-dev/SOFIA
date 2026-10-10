"""Desktop app (PySide6): live filter design with response plot, stage cards and netlist export."""

from __future__ import annotations

import html
import sys
import time
from pathlib import Path

try:
    from PySide6.QtCore import QSize, Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QAction, QColor, QFont, QGuiApplication, QKeySequence, QPalette
    from PySide6.QtWidgets import (
        QApplication,
        QButtonGroup,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPlainTextEdit,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QTabWidget,
        QToolButton,
        QVBoxLayout,
        QWidget,
    )
except ImportError as exc:  # pragma: no cover - depends on the install
    raise SystemExit('La interfaz necesita PySide6: pip install "sofia-filter-studio[gui]"') from exc

from .. import __version__
from ..design import design_filter
from ..board import BoardOptions, Mounting, bom_csv, build_board
from ..forms import (
    APPROXIMATIONS,
    DEFAULT_BANDS,
    KINDS,
    MOUNTINGS,
    OPAMPS,
    SERIES,
    SPEC_HINTS,
    TOPOLOGIES,
    FormError,
    netlist_filename,
    passband_edge_text,
    read_form,
)
from ..models import (
    DesignInputs,
    DesignResult,
    FilterKind,
    OpAmpModel,
    ResistorSeries,
    Topology,
)
from ..netlist import render_netlist, supply_voltage_for
from ..response import design_response, spec_bands
from ..synthesis import TOPOLOGY_NAMES
from ..units import format_quantity, format_resistor_value


class _PcbJob(QThread):
    """Places and routes the board off the GUI thread."""

    finished_job = Signal(object, object)

    def __init__(self, key, board) -> None:
        super().__init__()
        self.key = key
        self.board = board

    def run(self) -> None:
        from ..pcb import build_pcb

        try:
            outcome = build_pcb(self.board)
        except Exception as exc:  # reported in the tab
            outcome = exc
        self.finished_job.emit(self.key, outcome)


class InputError(ValueError):
    def __init__(self, message: str, *fields: QLineEdit) -> None:
        super().__init__(message)
        self.fields = fields


def _card(title: str, step: str | None = None) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 16)
    layout.setSpacing(10)
    header = QHBoxLayout()
    header.setSpacing(8)
    if step:
        badge = QLabel(step)
        badge.setObjectName("step")
        header.addWidget(badge)
    label = QLabel(title)
    label.setObjectName("cardTitle")
    header.addWidget(label)
    header.addStretch()
    layout.addLayout(header)
    return frame, layout


def _label(text: str, name: str | None = None, wrap: bool = False) -> QLabel:
    label = QLabel(text)
    if name:
        label.setObjectName(name)
    label.setWordWrap(wrap)
    return label


class QuantityField(QWidget):
    """Line edit that accepts engineering notation ('10n', '1.5k') followed by a unit label."""

    changed = Signal()

    def __init__(self, text: str, unit: str, tooltip: str = "") -> None:
        super().__init__()
        self.unit = unit
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.edit = QLineEdit(text)
        self.edit.setToolTip(tooltip or "Acepta notación de ingeniería: 10n, 4.7k, 1.5M, 1e-8")
        self.edit.textChanged.connect(self.changed)
        layout.addWidget(self.edit, 1)
        unit_label = _label(unit, "muted")
        unit_label.setMinimumWidth(18)
        layout.addWidget(unit_label)

    def text(self) -> str:
        return self.edit.text()

    def set_text(self, text: str) -> None:
        self.edit.setText(text)


def _clear_layout(layout) -> None:
    """Remove and destroy every widget of a layout right away (deleteLater alone leaves them painted)."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _set_invalid(edit: QLineEdit, invalid: bool) -> None:
    if edit.property("invalid") != invalid:
        edit.setProperty("invalid", invalid)
        edit.style().unpolish(edit)
        edit.style().polish(edit)


def _field(label: str, widget: QWidget, hint: str | None = None) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(4)
    layout.addWidget(_label(label))
    layout.addWidget(widget)
    if hint:
        layout.addWidget(_label(hint, "fieldHint", wrap=True))
    return box


def _combo(items: list[tuple], selected) -> QComboBox:
    combo = QComboBox()
    for value, text, *_ in items:
        combo.addItem(text, value)
    combo.setCurrentIndex([item[0] for item in items].index(selected))
    return combo


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        from .icons import app_icon, response_icon  # needs a QApplication

        self._response_icon = response_icon
        self.setWindowTitle(f"SOFIA Filter Studio {__version__}")
        self.setWindowIcon(app_icon())
        self.resize(1360, 860)
        self.setMinimumSize(1040, 680)
        self._result: DesignResult | None = None
        self._inputs: DesignInputs | None = None
        self._netlist = ""
        self._band_values = {kind: list(values) for kind, values in DEFAULT_BANDS.items()}
        self._current_kind = FilterKind.LOWPASS
        # Which single-edge filter the Fp/Fs fields were filled for.
        self._single_kind = FilterKind.LOWPASS
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self.recalculate)

        root = QWidget()
        root.setObjectName("root")
        layout = QHBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 8)
        layout.setSpacing(16)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_results(), 1)
        self.setCentralWidget(root)
        self._build_menu()
        self.statusBar().showMessage("Listo")
        self.recalculate()

    # Sidebar ------------------------------------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        content = QWidget()
        content.setObjectName("sidebarContent")
        column = QVBoxLayout(content)
        column.setContentsMargins(0, 0, 8, 0)
        column.setSpacing(12)

        title = _label("SOFIA", "appTitle")
        subtitle = _label("Diseño de filtros activos", "appSubtitle")
        column.addWidget(title)
        column.addWidget(subtitle)

        # 1. Filter type and approximation
        card, body = _card("¿Qué filtro necesitas?", "1")
        grid = QGridLayout()
        grid.setSpacing(8)
        self.kind_group = QButtonGroup(self)
        self.kind_group.setExclusive(True)
        for index, (kind, text) in enumerate(KINDS):
            button = QToolButton()
            button.setObjectName("kindButton")
            button.setText(text)
            button.setIcon(self._response_icon(kind))
            button.setIconSize(QSize(64, 36))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setCheckable(True)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setProperty("kind", kind.value)
            self.kind_group.addButton(button, index)
            grid.addWidget(button, index // 2, index % 2)
        self.kind_group.button(0).setChecked(True)
        self.kind_group.idClicked.connect(self._on_kind_changed)
        body.addLayout(grid)

        body.addWidget(_label("Aproximación"))
        approx_row = QHBoxLayout()
        approx_row.setSpacing(8)
        self.approx_group = QButtonGroup(self)
        for index, (_, name, detail) in enumerate(APPROXIMATIONS):
            button = QPushButton(f"{name}\n{detail}")
            button.setObjectName("segment")
            button.setCheckable(True)
            self.approx_group.addButton(button, index)
            approx_row.addWidget(button)
        self.approx_group.button(0).setChecked(True)
        self.approx_group.idClicked.connect(self.schedule)
        body.addLayout(approx_row)
        column.addWidget(card)

        # 2. Specification
        card, body = _card("Especificación", "2")
        single = QWidget()
        single_layout = QHBoxLayout(single)
        single_layout.setContentsMargins(0, 0, 0, 0)
        single_layout.setSpacing(10)
        self.fp = QuantityField("1k", "Hz")
        self.fs = QuantityField("2k", "Hz")
        single_layout.addWidget(_field("Frecuencia de paso Fp", self.fp))
        single_layout.addWidget(_field("Frecuencia de rechazo Fs", self.fs))
        # Only one of the two field groups is shown, so the card shrinks to what the filter needs.
        self.single_spec = single
        body.addWidget(single)

        band = QWidget()
        band_layout = QGridLayout(band)
        band_layout.setContentsMargins(0, 0, 0, 0)
        band_layout.setHorizontalSpacing(10)
        band_layout.setVerticalSpacing(6)
        self.fp1, self.fp2 = QuantityField("800", "Hz"), QuantityField("1.2k", "Hz")
        self.fs1, self.fs2 = QuantityField("500", "Hz"), QuantityField("2k", "Hz")
        band_layout.addWidget(_label("Banda de paso"), 0, 0, 1, 2)
        band_layout.addWidget(_field("Fp1", self.fp1), 1, 0)
        band_layout.addWidget(_field("Fp2", self.fp2), 1, 1)
        band_layout.addWidget(_label("Banda de rechazo"), 2, 0, 1, 2)
        band_layout.addWidget(_field("Fs1", self.fs1), 3, 0)
        band_layout.addWidget(_field("Fs2", self.fs2), 3, 1)
        self.band_spec = band
        band.setVisible(False)
        body.addWidget(band)
        self.spec_hint = _label(SPEC_HINTS[FilterKind.LOWPASS], "fieldHint", wrap=True)
        body.addWidget(self.spec_hint)

        gains = QHBoxLayout()
        gains.setSpacing(10)
        self.ripple = QuantityField("1", "dB", "Caída máxima permitida dentro de la banda de paso.")
        self.attenuation = QuantityField("40", "dB", "Atenuación mínima exigida en la banda de rechazo.")
        gains.addWidget(_field("Rizo máximo (Ap)", self.ripple))
        gains.addWidget(_field("Atenuación mínima (As)", self.attenuation))
        body.addLayout(gains)
        column.addWidget(card)

        # 3. Circuit
        card, body = _card("Circuito", "3")
        self.topology = _combo(TOPOLOGIES, Topology.AUTO)
        self.topology.setToolTip("Automática elige por etapa según su Q y el tipo de filtro.")
        body.addWidget(_field("Topología", self.topology))
        self.opamp = _combo(OPAMPS, OpAmpModel.TL082)
        body.addWidget(_field("Amplificador operacional", self.opamp))
        self.capacitor = QuantityField("10n", "F")
        body.addWidget(_field("Capacitor base", self.capacitor, "Punto de partida; cada etapa lo ajusta si es necesario."))
        self.mounting = _combo(MOUNTINGS, Mounting.SMD)
        self.mounting.setToolTip("Huellas del esquemático, la lista de materiales y la PCB.")
        body.addWidget(_field("Componentes de la placa", self.mounting))

        self.advanced_toggle = QToolButton()
        self.advanced_toggle.setObjectName("disclosure")
        self.advanced_toggle.setText("Opciones avanzadas")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.advanced_toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        body.addWidget(self.advanced_toggle)
        self.advanced = QWidget()
        advanced = QVBoxLayout(self.advanced)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setSpacing(8)
        self.series = _combo(SERIES, ResistorSeries.E96)
        advanced.addWidget(
            _field(
                "Serie de resistencias comerciales",
                self.series,
                "Un solo resistor comercial por posición. E96 mantiene el filtro dentro de la especificación.",
            )
        )
        self.auto_cap = QCheckBox("Ajustar el capacitor de cada etapa")
        self.auto_cap.setChecked(True)
        advanced.addWidget(self.auto_cap)
        self.margin = QCheckBox("Dejar margen para componentes comerciales")
        self.margin.setToolTip(
            "Reparte el orden que sobra entre las dos bandas: con resistencias comerciales el circuito cumple con holgura,\n"
            "pero el borde de la banda de paso ya no cae exacto en la frecuencia pedida."
        )
        advanced.addWidget(self.margin)
        self.advanced.setVisible(False)
        body.addWidget(self.advanced)
        self.advanced_toggle.toggled.connect(self._toggle_advanced)
        column.addWidget(card)
        column.addStretch()

        for field in (self.fp, self.fs, self.fp1, self.fp2, self.fs1, self.fs2, self.capacitor, self.ripple, self.attenuation):
            field.changed.connect(self.schedule)
        for combo in (self.topology, self.opamp, self.series):
            combo.currentIndexChanged.connect(self.schedule)
        self.auto_cap.toggled.connect(self.schedule)
        self.margin.toggled.connect(self.schedule)
        self.mounting.currentIndexChanged.connect(self._invalidate_schematic)

        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(380)
        return scroll

    def _toggle_advanced(self, open_: bool) -> None:
        self.advanced.setVisible(open_)
        self.advanced_toggle.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)

    # Results ------------------------------------------------------------------------------------
    def _build_results(self) -> QWidget:
        panel = QWidget()
        column = QVBoxLayout(panel)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(12)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(6)
        self.headline = _label("", "headline")
        titles.addWidget(self.headline)
        self.chips = QHBoxLayout()
        self.chips.setSpacing(6)
        chips_box = QWidget()
        chips_box.setLayout(self.chips)
        self.chips.setContentsMargins(0, 0, 0, 0)
        titles.addWidget(chips_box)
        header.addLayout(titles, 1)
        self.copy_button = QPushButton("Copiar netlist")
        self.copy_button.setObjectName("secondary")
        self.copy_button.clicked.connect(self.copy_netlist)
        self.save_button = QPushButton("Guardar netlist…")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self.save_netlist)
        header.addWidget(self.copy_button, 0, Qt.AlignmentFlag.AlignTop)
        header.addWidget(self.save_button, 0, Qt.AlignmentFlag.AlignTop)
        column.addLayout(header)

        self.error_banner = _label("", "errorBanner", wrap=True)
        self.error_banner.setVisible(False)
        column.addWidget(self.error_banner)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(10)

        plot_card, plot_body = _card("Respuesta en frecuencia")
        plot_header = QHBoxLayout()
        plot_header.addWidget(
            _label(
                "Zonas rojas: fuera de la especificación.  Rueda: zoom · arrastrar: mover · doble clic: ver todo.",
                "muted",
                wrap=True,
            ),
            1,
        )
        self.view_group = QButtonGroup(self)
        for index, (text, tip) in enumerate(
            (
                ("Completa", "Toda la respuesta, hasta donde llega la atenuación"),
                ("Banda de paso", "Acercamiento a la parte superior para ver el rizo"),
            )
        ):
            button = QPushButton(text)
            button.setObjectName("segmentSmall")
            button.setCheckable(True)
            button.setToolTip(tip)
            self.view_group.addButton(button, index)
            plot_header.addWidget(button)
        self.view_group.button(0).setChecked(True)
        plot_body.addLayout(plot_header)
        from .plot import ResponsePlot

        self.plot = ResponsePlot()
        self.view_group.idClicked.connect(lambda index: self.plot.set_passband_view(index == 1))
        self.plot.setToolTip("Rueda: zoom (Shift: solo dB, Ctrl: solo frecuencia) · arrastrar: mover · doble clic: ver todo")
        plot_body.addWidget(self.plot, 1)
        splitter.addWidget(plot_card)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.stages_area, self.stages_grid = self._scroll_grid()
        self.tabs.addTab(self.stages_area, "Etapas")
        self.tabs.addTab(self._build_schematic_tab(), "Esquemático")
        self.tabs.addTab(self._build_pcb_tab(), "PCB")
        self._schematic_key = None
        self._pcb_key = None
        self._pcb = None
        self._pcb_job: _PcbJob | None = None
        self._pcb_side = "top"
        self.tabs.currentChanged.connect(lambda _index: (self._refresh_schematic(), self._refresh_pcb()))
        netlist_tab = QWidget()
        netlist_layout = QVBoxLayout(netlist_tab)
        netlist_layout.setContentsMargins(0, 8, 0, 0)
        self.exact_values = QCheckBox(
            "Valores exactos, sin redondear: para comprobar el cálculo (en LTspice los bordes caen justo en las frecuencias pedidas)"
        )
        # Only a valid design on screen has a netlist to redo (after an error the old result stays around).
        self.exact_values.toggled.connect(lambda _checked: self._render_netlist() if self._netlist else None)
        netlist_layout.addWidget(self.exact_values)
        self.netlist_view = QPlainTextEdit()
        self.netlist_view.setObjectName("code")
        self.netlist_view.setReadOnly(True)
        self.netlist_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        netlist_layout.addWidget(self.netlist_view)
        self.tabs.addTab(netlist_tab, "Netlist")
        self.warnings_area, self.warnings_layout = self._scroll_column()
        self.tabs.addTab(self.warnings_area, "Avisos")
        self.details_area, self.details_layout = self._scroll_column()
        self.tabs.addTab(self.details_area, "Detalles")
        splitter.addWidget(self.tabs)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 4)
        column.addWidget(splitter, 1)
        return panel

    def _scroll_grid(self) -> tuple[QScrollArea, QGridLayout]:
        content = QWidget()
        content.setObjectName("stagesContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 10, 4, 4)
        grid.setSpacing(12)
        area = QScrollArea()
        area.setWidget(content)
        area.setWidgetResizable(True)
        return area, grid

    def _build_schematic_tab(self) -> QWidget:
        from .schematicview import SchematicView

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        bar = QHBoxLayout()
        bar.addWidget(_label("Rueda: zoom · arrastrar: mover · doble clic: ajustar", "muted"), 1)
        for text, what, tip in (
            ("Guardar para KiCad…", "kicad_sch", "Proyecto de KiCad (ZIP) con el esquemático"),
            ("Guardar SVG…", "svg", "Esquemático como imagen vectorial"),
            ("Guardar materiales…", "bom", "Lista de materiales (CSV) para comprar"),
        ):
            button = QPushButton(text)
            button.setObjectName("secondary")
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, what=what: self.save_export(what))
            bar.addWidget(button)
        layout.addLayout(bar)
        self.schematic_view = SchematicView()
        layout.addWidget(self.schematic_view, 1)
        self.schematic_tab = tab
        return tab

    def _build_pcb_tab(self) -> QWidget:
        from .schematicview import SchematicView

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(8)
        bar = QHBoxLayout()
        self.pcb_status = _label("La placa se rutea al abrir esta pestaña.", "muted", wrap=True)
        bar.addWidget(self.pcb_status, 1)
        self.pcb_side_group = QButtonGroup(self)
        for index, (text, side) in enumerate((("Arriba", "top"), ("Abajo", "bottom"))):
            button = QPushButton(text)
            button.setObjectName("segmentSmall")
            button.setCheckable(True)
            button.setProperty("side", side)
            self.pcb_side_group.addButton(button, index)
            bar.addWidget(button)
        self.pcb_side_group.button(0).setChecked(True)
        self.pcb_side_group.idClicked.connect(self._on_pcb_side)
        for text, what, tip in (
            ("Guardar PCB de KiCad…", "kicad_pcb", "Proyecto de KiCad (ZIP) con el esquemático y la placa ruteada"),
            ("Guardar Gerber…", "gerber", "Archivos de fabricación: Gerber y barrenos en un ZIP"),
            ("Guardar posiciones…", "cpl", "Posiciones de los componentes SMD para ensamble"),
        ):
            button = QPushButton(text)
            button.setObjectName("secondary")
            button.setToolTip(tip)
            button.clicked.connect(lambda _checked=False, what=what: self.save_pcb_file(what))
            bar.addWidget(button)
        layout.addLayout(bar)
        self.pcb_view = SchematicView()
        self.pcb_view.setBackgroundBrush(QColor("#0b1f17"))
        layout.addWidget(self.pcb_view, 1)
        self.pcb_tab = tab
        return tab

    def _on_pcb_side(self, index: int) -> None:
        self._pcb_side = ("top", "bottom")[index]
        self._show_pcb()

    def _refresh_pcb(self) -> None:
        if self.tabs.currentWidget() is not self.pcb_tab or self._result is None or not self._netlist:
            return
        key = (id(self._result), self.mounting.currentData())
        if key == self._pcb_key or (self._pcb_job is not None and self._pcb_job.key == key):
            return
        self.pcb_status.setText("Colocando y ruteando la placa…")
        job = _PcbJob(key, self._board())
        job.finished_job.connect(self._pcb_done)
        self._pcb_job = job
        job.start()

    def _pcb_done(self, key, outcome) -> None:
        job, self._pcb_job = self._pcb_job, None
        if job is not None:
            job.wait()
        current = (id(self._result), self.mounting.currentData()) if self._result is not None else None
        if key != current:
            self._refresh_pcb()
            return
        self._pcb_key = key
        if isinstance(outcome, Exception):
            self._pcb = None
            self.pcb_view.show_message(str(outcome))
            self.pcb_status.setText("No se pudo generar la placa.")
            return
        self._pcb = outcome
        self._show_pcb()
        routing = f"{len(outcome.unrouted)} conexiones sin rutear" if outcome.unrouted else "ruteo completo"
        rules = f"{len(outcome.problems)} avisos de reglas" if outcome.problems else "sin errores de reglas"
        parts = sum(1 for component in outcome.board.components if component.in_bom)
        self.pcb_status.setText(f"{outcome.width:.1f} × {outcome.height:.1f} mm · {parts} componentes · {len(outcome.vias)} vías · {routing} · {rules}")

    def _show_pcb(self) -> None:
        if self._pcb is not None:
            from ..pcb import to_svg as pcb_svg

            self.pcb_view.show_svg(pcb_svg(self._pcb, self._pcb_side))

    def save_pcb_file(self, what: str) -> None:
        if self._pcb is None:
            self.statusBar().showMessage("Abre la pestaña PCB y espera a que termine el ruteo.", 6000)
            return
        from ..kicad import project_zip
        from ..pcbfiles import gerber_zip, placement_csv
        from ..schematic import build_schematic

        base = self._default_filename().removesuffix(".cir")
        suffix, filters = {
            "kicad_pcb": ("_kicad.zip", "Proyecto de KiCad (*.zip)"),
            "gerber": ("_gerber.zip", "Gerber en ZIP (*.zip)"),
            "cpl": ("_posiciones.csv", "Posiciones CSV (*.csv)"),
        }[what]
        path, _ = QFileDialog.getSaveFileName(self, "Guardar", base + suffix, filters + ";;Todos los archivos (*)")
        if not path:
            return
        if what == "gerber":
            Path(path).write_bytes(gerber_zip(self._pcb, base))
        elif what == "kicad_pcb":
            Path(path).write_bytes(project_zip(build_schematic(self._pcb.board), base, self._pcb))
        else:
            Path(path).write_text(placement_csv(self._pcb), encoding="utf-8")
        self.statusBar().showMessage(f"Guardado en {path}", 8000)

    def _board(self):
        options = BoardOptions(Mounting(self.mounting.currentData()))
        return build_board(self._inputs, self._result, options)

    def _invalidate_schematic(self, *_args) -> None:
        self._schematic_key = None
        self._refresh_schematic()
        self._refresh_pcb()

    def _refresh_schematic(self) -> None:
        if self.tabs.currentWidget() is not self.schematic_tab or self._result is None or not self._netlist:
            return
        key = (id(self._result), self.mounting.currentData())
        if key == self._schematic_key:
            return
        from ..schematic import build_schematic, to_svg

        try:
            schematic = build_schematic(self._board())
        except ValueError as exc:
            self.schematic_view.show_message(str(exc))
        else:
            self.schematic_view.show_svg(to_svg(schematic, standalone=False, inline=True))
        self._schematic_key = key

    def save_export(self, what: str) -> None:
        if not self._netlist:
            return
        from ..kicad import project_zip
        from ..schematic import build_schematic, to_svg

        base = self._default_filename().removesuffix(".cir")
        suffix, filters = {
            "kicad_sch": ("_kicad.zip", "Proyecto de KiCad (*.zip)"),
            "svg": ("_esquematico.svg", "Imagen SVG (*.svg)"),
            "bom": ("_materiales.csv", "Lista de materiales CSV (*.csv)"),
        }[what]
        path, _ = QFileDialog.getSaveFileName(self, "Guardar", base + suffix, filters + ";;Todos los archivos (*)")
        if not path:
            return
        board = self._board()
        if what == "kicad_sch":
            Path(path).write_bytes(project_zip(build_schematic(board), base))
        else:
            content = bom_csv(board) if what == "bom" else to_svg(build_schematic(board))
            Path(path).write_text(content, encoding="utf-8")
        self.statusBar().showMessage(f"Guardado en {path}", 8000)

    def _scroll_column(self) -> tuple[QScrollArea, QVBoxLayout]:
        content = QWidget()
        content.setObjectName("stagesContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 10, 4, 4)
        layout.setSpacing(8)
        area = QScrollArea()
        area.setWidget(content)
        area.setWidgetResizable(True)
        return area, layout

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&Archivo")
        save = QAction("Guardar netlist…", self)
        save.setShortcut(QKeySequence.StandardKey.Save)
        save.triggered.connect(self.save_netlist)
        copy = QAction("Copiar netlist", self)
        copy.setShortcut(QKeySequence("Ctrl+Shift+C"))
        copy.triggered.connect(self.copy_netlist)
        leave = QAction("Salir", self)
        leave.setShortcut(QKeySequence.StandardKey.Quit)
        leave.triggered.connect(self.close)
        file_menu.addActions([save, copy])
        file_menu.addSeparator()
        file_menu.addAction(leave)
        help_menu = self.menuBar().addMenu("A&yuda")
        about = QAction("Acerca de SOFIA", self)
        about.triggered.connect(self._about)
        help_menu.addAction(about)

    # Behaviour ----------------------------------------------------------------------------------
    def schedule(self, *_args) -> None:
        self._timer.start()

    def _kind(self) -> FilterKind:
        return KINDS[self.kind_group.checkedId()][0]

    def _on_kind_changed(self, index: int) -> None:
        previous, kind = self._current_kind, KINDS[index][0]
        if previous in DEFAULT_BANDS:
            self._band_values[previous] = [f.text() for f in (self.fp1, self.fp2, self.fs1, self.fs2)]
        if kind in DEFAULT_BANDS:
            for field, value in zip((self.fp1, self.fp2, self.fs1, self.fs2), self._band_values[kind]):
                field.set_text(value)
        elif kind is not self._single_kind:
            # Fp/Fs were typed for the other single-edge filter (maybe before a detour through a band
            # filter): swap them so the spec stays valid.
            fp, fs = self.fp.text(), self.fs.text()
            self.fp.set_text(fs)
            self.fs.set_text(fp)
            self._single_kind = kind
        self._current_kind = kind
        single = kind in {FilterKind.LOWPASS, FilterKind.HIGHPASS}
        self.single_spec.setVisible(single)
        self.band_spec.setVisible(not single)
        self.spec_hint.setText(SPEC_HINTS[kind])
        self.schedule()

    def _text_fields(self) -> dict[str, QuantityField]:
        return {
            "fp": self.fp,
            "fs": self.fs,
            "fp1": self.fp1,
            "fp2": self.fp2,
            "fs1": self.fs1,
            "fs2": self.fs2,
            "ap": self.ripple,
            "as": self.attenuation,
            "cap": self.capacitor,
        }

    def read_inputs(self) -> DesignInputs:
        fields = self._text_fields()
        for field in fields.values():
            _set_invalid(field.edit, False)
        form = {name: field.text() for name, field in fields.items()}
        form.update(
            kind=self._kind().value,
            approximation=APPROXIMATIONS[self.approx_group.checkedId()][0].value,
            topology=self.topology.currentData(),
            opamp=self.opamp.currentData(),
            series=self.series.currentData(),
            auto_cap=self.auto_cap.isChecked(),
            margin=self.margin.isChecked(),
        )
        try:
            return read_form(form)
        except FormError as exc:
            raise InputError(str(exc), *(fields[name].edit for name in exc.fields)) from None

    def recalculate(self) -> None:
        try:
            inputs = self.read_inputs()
            started = time.perf_counter()
            result = design_filter(inputs)
        except InputError as exc:
            for edit in exc.fields:
                _set_invalid(edit, True)
            self._show_error(str(exc))
            return
        except ValueError as exc:
            self._show_error(f"No se pudo diseñar con estos valores: {exc}")
            return
        elapsed_ms = (time.perf_counter() - started) * 1e3
        self._inputs, self._result = inputs, result
        self._render_netlist()
        self.error_banner.setVisible(False)
        self.save_button.setEnabled(True)
        self.copy_button.setEnabled(True)
        self._update_header(inputs, result)
        self._update_plot(inputs, result)
        self._update_stages(result)
        self._update_warnings(result)
        self._update_details(inputs, result)
        self._schematic_key = None
        self._refresh_schematic()
        self._refresh_pcb()
        self.statusBar().showMessage(f"Diseño actualizado en {elapsed_ms:.0f} ms")

    def _render_netlist(self, *_args) -> None:
        if self._result is None:
            return
        exact = self.exact_values.isChecked()
        self._netlist = render_netlist(self._inputs, self._result, inline_model=True, exact_values=exact)
        self.netlist_view.setPlainText(self._netlist)

    def _show_error(self, message: str) -> None:
        # Drop the previous design so nothing on screen contradicts the current inputs.
        self._netlist = ""
        self.error_banner.setText(message)
        self.error_banner.setVisible(True)
        self.headline.setText("Revisa la especificación")
        _clear_layout(self.chips)
        _clear_layout(self.stages_grid)
        _clear_layout(self.warnings_layout)
        _clear_layout(self.details_layout)
        self.tabs.setTabText(self.tabs.indexOf(self.warnings_area), "Avisos")
        self._schematic_key = None
        self.schematic_view.show_message("Completa la especificación para ver el esquemático")
        self._pcb = None
        self._pcb_key = None
        self.pcb_view.show_message("Completa la especificación para ver la placa")
        self.plot.clear()
        self.netlist_view.clear()
        self.save_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.statusBar().showMessage("Revisa la especificación")

    def _update_header(self, inputs: DesignInputs, result: DesignResult) -> None:
        kind_name = dict(KINDS)[inputs.kind]
        approx = next(name for value, name, _ in APPROXIMATIONS if value is inputs.approximation)
        self.headline.setText(f"{kind_name} {approx} de orden {result.order}")
        _clear_layout(self.chips)
        stages = len(result.stages)
        topologies = []
        for stage in result.stages:
            name = TOPOLOGY_NAMES[stage.realization.topology]
            if name not in topologies:
                topologies.append(name)
        supply = supply_voltage_for(inputs)
        chips = [
            (f"{stages} etapa{'s' if stages != 1 else ''}", "chip"),
            (" + ".join(topologies), "chip"),
            (f"{inputs.opamp.value} · {supply:g} V", "chip"),
        ]
        warnings = len(result.warnings)
        chips.append(
            (f"{warnings} aviso{'s' if warnings != 1 else ''}", "chipWarn") if warnings else ("Sin avisos", "chipOk")
        )
        for text, name in chips:
            self.chips.addWidget(_label(text, name))
        self.chips.addStretch()

    def _update_plot(self, inputs: DesignInputs, result: DesignResult) -> None:
        freqs, gains = design_response(inputs, result, points_per_decade=160)
        passbands, stopbands = spec_bands(inputs, freqs[0], freqs[-1])
        self.plot.set_data(freqs, gains, passbands, stopbands, inputs.passband_ripple_db, inputs.stopband_attenuation_db)

    def _update_stages(self, result: DesignResult) -> None:
        _clear_layout(self.stages_grid)
        for index, stage in enumerate(result.stages):
            self.stages_grid.addWidget(self._stage_card(stage), index // 2, index % 2)
        self.stages_grid.setRowStretch(len(result.stages) // 2 + 1, 1)

    def _stage_card(self, stage) -> QFrame:
        realization = stage.realization
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)
        top = QHBoxLayout()
        top.setSpacing(6)
        title = _label(f"Etapa {stage.index}", "cardTitle")
        top.addWidget(title)
        top.addWidget(_label(TOPOLOGY_NAMES[realization.topology], "chip"))
        top.addWidget(_label("1er orden" if stage.order == 1 else "2º orden", "chip"))
        top.addStretch()
        layout.addLayout(top)
        metrics = [f"f0 {format_quantity(stage.natural_frequency_hz, 'Hz')}"]
        if stage.q is not None:
            metrics.append(f"Q {stage.q:.3f}")
        if realization.gain is not None:
            gain = realization.gain
            metrics.append(f"ganancia {abs(gain):.3g}" + (" (inversora)" if gain < 0 else ""))
        layout.addWidget(_label("   ·   ".join(metrics), "muted"))
        rows = []
        for name, value in realization.capacitor_values_f.items():
            rows.append(f"<tr><td><b>{html.escape(name)}</b></td><td>{format_quantity(value, 'F')}</td><td></td></tr>")
        for name, network in realization.resistor_networks.items():
            if network.connection == "single":
                parts = ""
            else:
                joiner = " ∥ " if network.connection == "parallel" else " + "
                parts = joiner.join(format_resistor_value(part) for part in network.parts_ohms)
            error = (network.realized_ohms - network.target_ohms) / network.target_ohms * 100
            detail = f"{parts}  ({error:+.2f} %)" if parts else f"({error:+.2f} %)"
            rows.append(
                f"<tr><td><b>{html.escape(name)}</b></td><td>{format_quantity(network.realized_ohms, 'Ω')}</td>"
                f"<td style='color:#6B7385'>{html.escape(detail)}</td></tr>"
            )
        table = QLabel("<table cellspacing='0' cellpadding='3'>" + "".join(rows) + "</table>")
        table.setTextFormat(Qt.TextFormat.RichText)
        table.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(table)
        return frame

    def _update_warnings(self, result: DesignResult) -> None:
        _clear_layout(self.warnings_layout)
        if result.warnings:
            for warning in result.warnings:
                self.warnings_layout.addWidget(_label(f"⚠  {warning}", "warningCard", wrap=True))
        else:
            self.warnings_layout.addWidget(_label("✓  Todo en orden: el diseño no tiene avisos.", "okCard", wrap=True))
        self.warnings_layout.addStretch()
        count = len(result.warnings)
        self.tabs.setTabText(self.tabs.indexOf(self.warnings_area), f"Avisos ({count})" if count else "Avisos")

    def _update_details(self, inputs: DesignInputs, result: DesignResult) -> None:
        _clear_layout(self.details_layout)
        summary = result.summary
        ripple, attenuation = summary["design_ripple_db"], summary["design_attenuation_db"]
        rows = [
            ("Orden del filtro", str(result.order)),
            ("Atenuación en el borde de paso", passband_edge_text(inputs, ripple)),
            ("Atenuación en el borde de rechazo", f"{attenuation:.2f} dB  (sobran {attenuation - inputs.stopband_attenuation_db:.2f} dB)"),
            ("Épsilon (rizo pedido)", f"{result.epsilon:.5f}"),
            ("Selectividad", f"{summary['ratio']:.4g}"),
            ("Alimentación", f"{supply_voltage_for(inputs):g} V, tierra virtual en {supply_voltage_for(inputs) / 2:g} V"),
        ]
        if "center_frequency_hz" in summary:
            rows.insert(2, ("Frecuencia central", format_quantity(summary["center_frequency_hz"], "Hz")))
            rows.insert(3, ("Ancho de banda", format_quantity(summary["bandwidth_hz"], "Hz")))
        recommended = ", ".join(summary.get("recommended_opamps", [])) or "ninguno"
        rows.append(("Opamps adecuados a esta frecuencia", recommended))
        info = "".join(f"<tr><td style='color:#6B7385'>{a}</td><td><b>{html.escape(b)}</b></td></tr>" for a, b in rows)
        poles = "".join(
            f"<tr><td>{index}</td><td>{pole.real:,.2f}</td><td>{pole.imag:+,.2f} j</td></tr>"
            for index, pole in enumerate(result.poles, start=1)
        )
        text = (
            f"<table cellspacing='0' cellpadding='4'>{info}</table>"
            "<p style='margin-top:12px'><b>Polos (rad/s)</b></p>"
            f"<table cellspacing='0' cellpadding='3'><tr style='color:#6B7385'><td>#</td><td>real</td><td>imaginaria</td></tr>{poles}</table>"
        )
        label = QLabel(text)
        label.setTextFormat(Qt.TextFormat.RichText)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        frame = QFrame()
        frame.setObjectName("card")
        box = QVBoxLayout(frame)
        box.setContentsMargins(16, 14, 16, 14)
        box.addWidget(label)
        self.details_layout.addWidget(frame)
        self.details_layout.addStretch()

    def _default_filename(self) -> str:
        return netlist_filename(self._inputs, self._result)

    def save_netlist(self) -> None:
        if not self._netlist:
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Guardar netlist",
            netlist_filename(self._inputs, self._result, self.exact_values.isChecked()),
            "Netlist SPICE (*.cir *.sp);;Todos los archivos (*)",
        )
        if not path:
            return
        Path(path).write_text(self._netlist + "\n", encoding="utf-8")
        self.statusBar().showMessage(f"Netlist guardado en {path}", 8000)

    def copy_netlist(self) -> None:
        if self._netlist:
            QGuiApplication.clipboard().setText(self._netlist)
            self.statusBar().showMessage("Netlist copiado al portapapeles", 5000)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        if self._pcb_job is not None:
            self._pcb_job.wait()
        super().closeEvent(event)

    def _about(self) -> None:
        QMessageBox.about(
            self,
            "Acerca de SOFIA",
            f"<h3>SOFIA Filter Studio {__version__}</h3>"
            "<p>Síntesis de filtros activos Butterworth y Chebyshev con Sallen-Key, MFB, Tow-Thomas y Antoniou, "
            "y exportación de netlists SPICE listos para LTspice o ngspice.</p>",
        )


def _light_palette() -> QPalette:
    from . import theme

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(theme.BACKGROUND))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(theme.TEXT))
    palette.setColor(QPalette.ColorRole.Base, QColor(theme.SURFACE))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(theme.BACKGROUND))
    palette.setColor(QPalette.ColorRole.Text, QColor(theme.TEXT))
    palette.setColor(QPalette.ColorRole.Button, QColor(theme.SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(theme.TEXT))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(theme.ACCENT))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("white"))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(theme.TEXT))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor("white"))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(theme.MUTED))
    return palette


def create_application(argv: list[str] | None = None) -> "QApplication":
    from . import theme

    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("SOFIA Filter Studio")
    # Links the window to the Linux menu entry (sofia-filter-studio.desktop) for its icon on Wayland.
    app.setDesktopFileName("sofia-filter-studio")
    app.setStyle("Fusion")
    app.setPalette(_light_palette())
    font = QFont("Segoe UI" if sys.platform == "win32" else app.font().family())
    font.setPointSizeF(10)
    app.setFont(font)
    from .icons import combo_arrow_file

    arrow = f'QComboBox::down-arrow {{ image: url("{combo_arrow_file()}"); width: 10px; height: 6px; }}'
    app.setStyleSheet(theme.STYLE_SHEET + arrow)
    return app


def main() -> None:
    app = create_application()
    window = MainWindow()
    window.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
