"""Status badge / pill widget for rendering test, gate, and release states."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy

from tools.gui import theme


class StatusPill(QLabel):
    """Badge widget for rendering operational status (PASS, FAIL, STALE, etc.)."""

    STATUS_STYLES = {
        "PASS": (theme.COLOR_PASS, "#064e3b", "#ffffff"),
        "OK": (theme.COLOR_PASS, "#064e3b", "#ffffff"),
        "CURRENT": (theme.COLOR_PASS, "#064e3b", "#ffffff"),
        "READY": (theme.COLOR_PRIMARY, "#1e3a8a", "#ffffff"),
        "ACTIVE": (theme.COLOR_PRIMARY, "#1e3a8a", "#ffffff"),
        "RUNNING": (theme.COLOR_PRIMARY, "#1e3a8a", "#ffffff"),
        "FAIL": (theme.COLOR_FAIL, "#4c0519", "#ffffff"),
        "ERROR": (theme.COLOR_FAIL, "#4c0519", "#ffffff"),
        "BLOCKED": (theme.COLOR_FAIL, "#4c0519", "#ffffff"),
        "MODIFIED": (theme.COLOR_FAIL, "#4c0519", "#ffffff"),
        "ADVISORY": (theme.COLOR_WARN, "#451a03", "#ffffff"),
        "WARN": (theme.COLOR_WARN, "#451a03", "#ffffff"),
        "STALE": (theme.COLOR_WARN, "#451a03", "#ffffff"),
        "INCOMPLETE": (theme.COLOR_WARN, "#451a03", "#ffffff"),
        "SKIPPED": (theme.COLOR_SKIPPED, "#18181b", "#d4d4d8"),
        "DISABLED": (theme.COLOR_SKIPPED, "#18181b", "#d4d4d8"),
        "NOT_TESTED": (theme.COLOR_SKIPPED, "#18181b", "#d4d4d8"),
    }

    def __init__(self, status: str = "READY", text: str = ""):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(22)
        self.setStatus(status, text)

    def setStatus(self, status: str, custom_text: str = ""):
        key = status.upper().replace(" ", "_")
        border, bg, text_col = self.STATUS_STYLES.get(key, ("#52525b", "#27272a", "#f4f4f5"))
        display = custom_text or status

        self.setText(f" {display} ")
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg};
                color: {text_col};
                border: 1px solid {border};
                border-radius: 9px;
                padding: 2px 10px;
                font-size: 11px;
                font-weight: 600;
            }}
        """)
