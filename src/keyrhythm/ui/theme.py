from __future__ import annotations

from PySide6.QtGui import QColor


COLORS = {
    "background": QColor("#070914"),
    "panel": QColor("#101629"),
    "panel_alt": QColor("#151d36"),
    "cyan": QColor("#3DEBFF"),
    "blue": QColor("#4387FF"),
    "magenta": QColor("#F04BFF"),
    "text": QColor("#F4F7FF"),
    "muted": QColor("#8C99B8"),
    "line": QColor("#283552"),
}


APP_STYLE = """
QWidget { background: #070914; color: #F4F7FF; font-family: "Segoe UI", "Microsoft YaHei UI"; font-size: 14px; }
QLabel { background: transparent; }
QMainWindow, QDialog { background: #070914; }
QLabel#title { font-size: 26px; font-weight: 700; color: #FFFFFF; }
QLabel#eyebrow { color: #3DEBFF; font-size: 11px; font-weight: 700; }
QLabel#muted { color: #8C99B8; }
QFrame#panel, QWidget#panel { background: #101629; border: 1px solid #263250; border-radius: 14px; }
QPushButton { background: #18213A; border: 1px solid #334268; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: #202C4C; border-color: #3DEBFF; }
QPushButton:pressed { background: #0E7892; }
QPushButton#primary { color: #07111B; background: #3DEBFF; border-color: #3DEBFF; }
QPushButton#primary:hover { background: #77F3FF; }
QLineEdit, QComboBox, QSpinBox { background: #101629; border: 1px solid #334268; border-radius: 8px; padding: 8px 10px; selection-background-color: #367DFF; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus { border-color: #3DEBFF; }
QComboBox QAbstractItemView { background: #101629; border: 1px solid #334268; selection-background-color: #263E70; }
QTableWidget { background: #0B1020; alternate-background-color: #10172A; border: 1px solid #263250; border-radius: 10px; gridline-color: #1C2944; selection-background-color: #1E5070; }
QHeaderView::section { background: #151D36; color: #9BA9C7; border: 0; border-bottom: 1px solid #334268; padding: 9px; font-weight: 600; }
QScrollBar:vertical { width: 10px; background: #0A0F1F; }
QScrollBar::handle:vertical { background: #314063; border-radius: 5px; min-height: 24px; }
QSlider::groove:horizontal { height: 5px; background: #263250; border-radius: 2px; }
QSlider::handle:horizontal { width: 16px; margin: -6px 0; background: #3DEBFF; border-radius: 8px; }
QProgressBar { background: #11182B; border: 0; border-radius: 3px; height: 6px; text-align: center; }
QProgressBar::chunk { background: #3DEBFF; border-radius: 3px; }
QStatusBar { color: #8C99B8; background: #080C18; }
QToolTip { color: #F4F7FF; background: #151D36; border: 1px solid #3DEBFF; padding: 5px; }
"""


def apply_theme(application) -> None:
    application.setStyle("Fusion")
    application.setStyleSheet(APP_STYLE)
