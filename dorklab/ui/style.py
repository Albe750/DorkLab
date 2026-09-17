"""Foglio di stile dell'applicazione, con varianti chiara e scura."""

from __future__ import annotations

LIGHT = {
    "bg": "#f6f7f9", "panel": "#ffffff", "fg": "#1a1c21", "muted": "#6b7280",
    "line": "#dfe2e8", "accent": "#3d7bff", "accent_fg": "#ffffff",
    "chip": "#eef1f6", "chip_line": "#d3d9e3", "danger": "#c0392b",
    "ok": "#16a34a", "warn": "#d97706", "input": "#ffffff",
}

DARK = {
    "bg": "#15171c", "panel": "#1c1f26", "fg": "#e7eaf0", "muted": "#98a0ad",
    "line": "#2b2f38", "accent": "#5b8dff", "accent_fg": "#0b1020",
    "chip": "#242832", "chip_line": "#343a46", "danger": "#ef5350",
    "ok": "#4ade80", "warn": "#fbbf24", "input": "#1f232b",
}

TEMPLATE = """
QWidget {{
    background: {bg};
    color: {fg};
    font-size: 10.5pt;
}}
QMainWindow, QDialog {{ background: {bg}; }}

QLabel#title {{ font-size: 15pt; font-weight: 600; }}
QLabel#subtitle {{ color: {muted}; }}
QLabel#sectionTitle {{ font-weight: 600; padding: 2px 0; }}
QLabel#hint {{ color: {muted}; font-size: 9.5pt; }}

QFrame#panel, QGroupBox {{
    background: {panel};
    border: 1px solid {line};
    border-radius: 10px;
}}
QGroupBox {{ margin-top: 14px; padding: 14px 12px 12px; font-weight: 600; }}
QGroupBox::title {{
    subcontrol-origin: margin; left: 12px; padding: 0 6px; color: {muted};
}}

QTabWidget::pane {{
    border: 1px solid {line}; border-radius: 10px; background: {panel}; top: -1px;
}}
QTabBar::tab {{
    background: transparent; color: {muted}; padding: 9px 18px;
    border: 1px solid transparent; border-bottom: none;
    border-top-left-radius: 9px; border-top-right-radius: 9px; margin-right: 2px;
}}
QTabBar::tab:selected {{
    background: {panel}; color: {fg};
    border-color: {line}; font-weight: 600;
}}
QTabBar::tab:hover:!selected {{ color: {fg}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {input}; border: 1px solid {line};
    border-radius: 7px; padding: 6px 9px; selection-background-color: {accent};
}}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QSpinBox:focus {{
    border-color: {accent};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {panel}; border: 1px solid {line};
    selection-background-color: {accent}; selection-color: {accent_fg};
}}

QPushButton {{
    background: {panel}; border: 1px solid {line}; border-radius: 7px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {accent}; }}
QPushButton:disabled {{ color: {muted}; border-color: {line}; }}
QPushButton#primary {{
    background: {accent}; color: {accent_fg}; border-color: {accent}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {accent}; }}
QPushButton#danger {{ color: {danger}; }}
QPushButton#linkish {{
    background: transparent; border: none; color: {accent}; padding: 3px 6px;
    text-align: left;
}}

/* ---------------------------------------------------------- bolle (chip) */
QPushButton#bubble {{
    background: {chip}; border: 1px solid {chip_line}; border-radius: 13px;
    padding: 5px 13px; color: {fg};
}}
QPushButton#bubble:hover {{ border-color: {accent}; color: {accent}; }}
QPushButton#bubble:checked {{
    background: {accent}; border-color: {accent}; color: {accent_fg};
}}
QPushButton#bubble:disabled {{ color: {muted}; border-style: dashed; }}
QPushButton#bubbleSensitive {{
    background: {chip}; border: 1px solid {warn}; border-radius: 13px;
    padding: 5px 13px; color: {fg};
}}
QPushButton#bubbleSensitive:checked {{
    background: {warn}; border-color: {warn}; color: #14161a;
}}

QFrame#chip {{
    background: {chip}; border: 1px solid {chip_line}; border-radius: 13px;
}}
QFrame#chip:hover {{ border-color: {accent}; }}
QFrame#chipNegated {{
    background: {chip}; border: 1px dashed {danger}; border-radius: 13px;
}}
QLabel#chipLabel {{ color: {muted}; font-weight: 600; font-size: 9.5pt; }}
QLineEdit#chipValue {{
    background: transparent; border: none; padding: 1px 2px; min-width: 40px;
}}
QPushButton#chipBtn {{
    background: transparent; border: none; color: {muted};
    padding: 0 4px; font-weight: 700;
}}
QPushButton#chipBtn:hover {{ color: {danger}; }}

QFrame#canvas {{
    background: {panel}; border: 1px dashed {line}; border-radius: 10px;
}}

QPlainTextEdit#preview {{
    font-family: "JetBrains Mono", "Fira Code", "DejaVu Sans Mono", monospace;
    font-size: 10pt; background: {input};
}}

QTableView, QTreeWidget, QListWidget {{
    background: {panel}; border: 1px solid {line}; border-radius: 9px;
    gridline-color: {line}; selection-background-color: {accent};
    selection-color: {accent_fg}; alternate-background-color: {chip};
}}
QHeaderView::section {{
    background: {bg}; color: {muted}; border: none;
    border-bottom: 1px solid {line}; padding: 7px 9px; font-weight: 600;
}}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{
    background: {chip_line}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {muted}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{
    background: {chip_line}; border-radius: 5px; min-width: 30px;
}}

QProgressBar {{
    border: 1px solid {line}; border-radius: 7px; text-align: center;
    background: {input}; height: 16px;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 6px; }}

QCheckBox, QRadioButton {{ spacing: 7px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 15px; height: 15px; }}
QToolTip {{
    background: {panel}; color: {fg}; border: 1px solid {line};
    padding: 5px 8px; border-radius: 6px;
}}
QSplitter::handle {{ background: transparent; }}
QStatusBar {{ color: {muted}; }}
QStatusBar::item {{ border: none; }}
"""


def stylesheet(theme: str = "auto", dark_hint: bool = False) -> str:
    """Restituisce il foglio di stile per il tema richiesto."""
    if theme == "dark" or (theme == "auto" and dark_hint):
        palette = DARK
    else:
        palette = LIGHT
    return TEMPLATE.format(**palette)


def palette_for(theme: str = "auto", dark_hint: bool = False) -> dict:
    if theme == "dark" or (theme == "auto" and dark_hint):
        return DARK
    return LIGHT
