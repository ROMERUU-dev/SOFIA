"""Colors and Qt style sheet of the desktop app."""

BACKGROUND = "#F3F5F9"
SURFACE = "#FFFFFF"
BORDER = "#E2E6EE"
TEXT = "#1E2533"
MUTED = "#6B7385"
ACCENT = "#2F6FED"
ACCENT_SOFT = "#EAF1FE"
ACCENT_DARK = "#1E4FBF"
SUCCESS = "#15803D"
SUCCESS_SOFT = "#E8F6EE"
WARNING = "#B45309"
WARNING_SOFT = "#FDF3E4"
DANGER = "#C2410C"
DANGER_SOFT = "#FDECE7"
FORBIDDEN = "#E5484D"
GRID = "#EDF0F5"
GRID_STRONG = "#DCE1EA"

STYLE_SHEET = f"""
QWidget {{
    color: {TEXT};
    font-size: 10pt;
}}
QMainWindow, QWidget#root, QWidget#sidebarContent, QWidget#stagesContent {{
    background: {BACKGROUND};
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QLabel#appTitle {{
    font-size: 17pt;
    font-weight: 700;
    color: {TEXT};
}}
QLabel#appSubtitle, QLabel#muted, QLabel#fieldHint {{
    color: {MUTED};
}}
QLabel#fieldHint {{
    font-size: 9pt;
}}
QLabel#cardTitle {{
    font-size: 11pt;
    font-weight: 600;
}}
QLabel#step {{
    color: white;
    background: {ACCENT};
    border-radius: 11px;
    font-weight: 700;
    min-width: 22px;
    max-width: 22px;
    min-height: 22px;
    max-height: 22px;
    qproperty-alignment: AlignCenter;
}}
QLabel#headline {{
    font-size: 16pt;
    font-weight: 700;
}}
QLabel#chip {{
    background: {ACCENT_SOFT};
    color: {ACCENT_DARK};
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}}
QLabel#chipOk {{
    background: {SUCCESS_SOFT};
    color: {SUCCESS};
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}}
QLabel#chipWarn {{
    background: {WARNING_SOFT};
    color: {WARNING};
    border-radius: 10px;
    padding: 3px 10px;
    font-weight: 600;
}}
QLabel#errorBanner {{
    background: {DANGER_SOFT};
    color: {DANGER};
    border: 1px solid #F6C9B8;
    border-radius: 10px;
    padding: 10px 14px;
    font-weight: 600;
}}
QLabel#warningCard {{
    background: {WARNING_SOFT};
    border: 1px solid #F3DDB8;
    border-radius: 10px;
    padding: 10px 14px;
}}
QLabel#okCard {{
    background: {SUCCESS_SOFT};
    border: 1px solid #C6E8D2;
    border-radius: 10px;
    padding: 10px 14px;
    color: {SUCCESS};
}}
QLineEdit, QComboBox, QDoubleSpinBox, QSpinBox {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 5px 8px;
    min-height: 22px;
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus, QDoubleSpinBox:focus, QSpinBox:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit[invalid="true"] {{
    border: 1px solid {DANGER};
    background: {DANGER_SOFT};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {BORDER};
    background: {SURFACE};
    selection-background-color: {ACCENT_SOFT};
    selection-color: {TEXT};
    outline: none;
}}
QToolButton#kindButton {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 4px 6px 4px;
    font-weight: 600;
}}
QToolButton#kindButton:hover {{
    border: 1px solid {ACCENT};
}}
QToolButton#kindButton:checked {{
    background: {ACCENT_SOFT};
    border: 2px solid {ACCENT};
    color: {ACCENT_DARK};
}}
QPushButton#segment {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 9px;
    padding: 7px 10px;
    text-align: left;
}}
QPushButton#segment:checked {{
    background: {ACCENT_SOFT};
    border: 2px solid {ACCENT};
    color: {ACCENT_DARK};
}}
QPushButton#segmentSmall {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 4px 12px;
    color: {MUTED};
    font-weight: 600;
}}
QPushButton#segmentSmall:checked {{
    background: {ACCENT_SOFT};
    border: 1px solid {ACCENT};
    color: {ACCENT_DARK};
}}
QPushButton#primary {{
    background: {ACCENT};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-weight: 600;
}}
QPushButton#primary:hover {{
    background: {ACCENT_DARK};
}}
QPushButton#primary:disabled {{
    background: #A9C1F5;
}}
QPushButton#secondary {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
}}
QPushButton#secondary:hover {{
    border: 1px solid {ACCENT};
    color: {ACCENT_DARK};
}}
QPushButton#secondary:disabled {{
    color: #A6ADBB;
    background: {BACKGROUND};
}}
QToolButton#disclosure {{
    border: none;
    color: {ACCENT_DARK};
    font-weight: 600;
    padding: 2px 0px;
}}
QCheckBox {{
    spacing: 8px;
}}
QTabWidget::pane {{
    border: none;
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {MUTED};
    padding: 8px 16px;
    margin-right: 2px;
    border: none;
    border-bottom: 2px solid transparent;
    font-weight: 600;
}}
QTabBar::tab:selected {{
    color: {ACCENT_DARK};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover {{
    color: {TEXT};
}}
QPlainTextEdit#code {{
    font-family: "Cascadia Mono", Consolas, "DejaVu Sans Mono", monospace;
    font-size: 9.5pt;
    background: #FAFBFD;
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 6px;
}}
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #CBD2DE;
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QStatusBar {{
    color: {MUTED};
    background: {BACKGROUND};
}}
QToolTip {{
    background: {TEXT};
    color: white;
    border: none;
    padding: 6px 8px;
}}
"""
