"""Theme, colors, and styling for the PCB-Project-Template desktop GUI."""

from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QApplication

# Color constants
COLOR_BG_DARK = "#101216"       # Deep obsidian window background
COLOR_BG_SURFACE = "#171a21"    # Elevated card / panel background
COLOR_BG_CARD = "#1f232c"       # Input / table alternate background
COLOR_BORDER = "#2b303d"        # Subtle container border
COLOR_TEXT_PRIMARY = "#f4f4f6"  # Bright readable primary text
COLOR_TEXT_MUTED = "#9ba1b0"    # Crisp secondary text
COLOR_PRIMARY = "#3b82f6"       # Blue 500
COLOR_PRIMARY_HOVER = "#2563eb" # Blue 600
COLOR_PASS = "#10b981"          # Emerald 500
COLOR_FAIL = "#ef4444"          # Crimson Red 500
COLOR_WARN = "#f59e0b"          # Amber 500
COLOR_SKIPPED = "#71717a"       # Neutral Zinc 500

STYLESHEET = f"""
QMainWindow, QDialog {{
    background-color: {COLOR_BG_DARK};
    color: {COLOR_TEXT_PRIMARY};
}}

QWidget {{
    font-family: "Helvetica Neue", Arial, Helvetica;
    font-size: 13px;
    color: {COLOR_TEXT_PRIMARY};
}}

QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QFrame#card {{
    background-color: {COLOR_BG_SURFACE};
    border: 1px solid {COLOR_BORDER};
    border-radius: 8px;
    padding: 16px;
}}

QFrame#sidebar {{
    background-color: #121419;
    border-right: 1px solid #242935;
}}

QLabel#h1 {{
    font-size: 22px;
    font-weight: 700;
    color: {COLOR_TEXT_PRIMARY};
    letter-spacing: -0.3px;
}}

QLabel#h2 {{
    font-size: 15px;
    font-weight: 600;
    color: {COLOR_TEXT_PRIMARY};
}}

QLabel#muted {{
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
}}

QLabel#code {{
    font-family: Menlo, Monaco, "Courier New", monospace;
    font-size: 12px;
    background-color: #13151b;
    border: 1px solid #252a36;
    padding: 4px 8px;
    border-radius: 5px;
    color: #e4e4e7;
}}

QPushButton {{
    background-color: {COLOR_BG_CARD};
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid #323847;
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 500;
    font-size: 13px;
}}

QPushButton:hover {{
    background-color: #282d38;
    border-color: #40485a;
}}

QPushButton:pressed {{
    background-color: #1a1d25;
}}

QPushButton:disabled {{
    background-color: #14161c;
    color: #555b6a;
    border-color: #222631;
}}

QPushButton#primary {{
    background-color: {COLOR_PRIMARY};
    color: #ffffff;
    border: 1px solid #3b82f6;
    font-weight: 600;
}}

QPushButton#primary:hover {{
    background-color: {COLOR_PRIMARY_HOVER};
    border-color: #60a5fa;
}}

QPushButton#primary:disabled {{
    background-color: #1a2744;
    color: #5b74a3;
    border-color: #24355a;
}}

QLineEdit, QComboBox, QSpinBox {{
    background-color: #12141a;
    color: {COLOR_TEXT_PRIMARY};
    border: 1px solid #2b303e;
    border-radius: 6px;
    padding: 7px 11px;
    selection-background-color: {COLOR_PRIMARY};
}}

QLineEdit:focus, QComboBox:focus {{
    border: 1px solid #3b82f6;
    background-color: #14171f;
}}

QComboBox::drop-down {{
    border: none;
    padding-right: 10px;
}}

QTableWidget {{
    background-color: #12141a;
    alternate-background-color: #161921;
    border: 1px solid #262b37;
    border-radius: 6px;
    gridline-color: transparent;
    color: {COLOR_TEXT_PRIMARY};
    selection-background-color: #1e3a8a;
    selection-color: #ffffff;
    outline: none;
}}

QTableWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid #1c202a;
}}

QTableWidget::item:selected {{
    background-color: #1e3a8a;
    color: #ffffff;
}}

QHeaderView::section {{
    background-color: {COLOR_BG_SURFACE};
    color: {COLOR_TEXT_MUTED};
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #2b303d;
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.4px;
}}

QPlainTextEdit {{
    background-color: #0c0e12;
    color: #e2e4e9;
    font-family: Menlo, Monaco, "Courier New", monospace;
    font-size: 12px;
    border: 1px solid #252a36;
    border-radius: 6px;
    padding: 10px;
}}

QProgressBar {{
    background-color: #14161c;
    border: 1px solid #262b37;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    height: 12px;
}}

QProgressBar::chunk {{
    background-color: {COLOR_PRIMARY};
    border-radius: 3px;
}}

QStatusBar {{
    background-color: #101216;
    border-top: 1px solid #20242e;
    color: {COLOR_TEXT_MUTED};
    font-size: 12px;
    padding: 2px 8px;
}}

QSplitter::handle {{
    background-color: #20242e;
}}

QSplitter::handle:horizontal {{
    width: 3px;
}}

QSplitter::handle:vertical {{
    height: 3px;
}}

QSplitter::handle:hover {{
    background-color: #3b82f6;
}}

QScrollBar:vertical {{
    background: #101216;
    width: 8px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background: #2b303d;
    min-height: 24px;
    border-radius: 4px;
}}

QScrollBar::handle:vertical:hover {{
    background: #3f475a;
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar:horizontal {{
    background: #101216;
    height: 8px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background: #2b303d;
    min-width: 24px;
    border-radius: 4px;
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QCheckBox {{
    color: {COLOR_TEXT_PRIMARY};
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #333947;
    background-color: #12141a;
}}

QCheckBox::indicator:checked {{
    background-color: {COLOR_PRIMARY};
    border-color: #3b82f6;
}}
"""


def apply_theme(app: QApplication) -> None:
    """Apply the application palette and stylesheet to the given QApplication."""
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(COLOR_BG_DARK))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Base, QColor("#12141a"))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(COLOR_BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(COLOR_BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Text, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.Button, QColor(COLOR_BG_SURFACE))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(COLOR_TEXT_PRIMARY))
    palette.setColor(QPalette.ColorRole.BrightText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(COLOR_PRIMARY))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    app.setPalette(palette)
    app.setFont(QFont("Helvetica Neue", 13))
    app.setStyleSheet(STYLESHEET)
