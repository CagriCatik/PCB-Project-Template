"""Navigation sidebar widget for the main window."""

from typing import List, Tuple

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from tools.gui import icons, theme


class SidebarButton(QPushButton):
    """Navigation button in the sidebar with vector icon and active indicators."""

    def __init__(self, text: str, icon_name: str, page_index: int):
        super().__init__(f"  {text}")
        self.icon_name = icon_name
        self.page_index = page_index
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self._update_style(False)

    def set_active(self, active: bool):
        self.setChecked(active)
        self._update_style(active)

    def _update_style(self, active: bool):
        bg = "#1e3a8a" if active else "transparent"
        fg = "#ffffff" if active else "#9ba1b0"
        border_left = "3px solid #3b82f6" if active else "3px solid transparent"
        weight = "600" if active else "500"
        icon_color = "#ffffff" if active else "#9ba1b0"

        self.setIcon(icons.get_icon(self.icon_name, icon_color, 16))
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: none;
                border-left: {border_left};
                border-radius: 6px;
                padding: 10px 14px;
                text-align: left;
                font-size: 13px;
                font-weight: {weight};
            }}
            QPushButton:hover {{
                background-color: {"#1e3a8a" if active else "#1a1e27"};
                color: #ffffff;
            }}
        """)


class Sidebar(QFrame):
    """Sidebar navigation container."""

    page_changed = Signal(int)

    NAV_ITEMS: List[Tuple[str, str]] = [
        ("Dashboard", "dashboard"),
        ("New Project", "new_project"),
        ("Projects", "folder"),
        ("Verification", "shield_check"),
        ("Manufacturing", "manufacturing"),
        ("Settings", "settings"),
    ]

    def __init__(self):
        super().__init__()
        self.setObjectName("sidebar")
        self.setFixedWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 16)
        layout.setSpacing(6)

        # Header branding
        title = QLabel("PCB Project Kit")
        title.setObjectName("h2")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #f4f4f5;")
        layout.addWidget(title)

        subtitle = QLabel("KiCad 10.0.7 · v2.0.0")
        subtitle.setObjectName("muted")
        layout.addWidget(subtitle)

        layout.addSpacing(16)

        # Navigation buttons
        self._buttons: List[SidebarButton] = []
        for idx, (label, icon_name) in enumerate(self.NAV_ITEMS):
            btn = SidebarButton(label, icon_name, idx)
            btn.clicked.connect(lambda checked=False, i=idx: self._on_btn_clicked(i))
            self._buttons.append(btn)
            layout.addWidget(btn)

        layout.addStretch()

        # Set default active
        if self._buttons:
            self._buttons[0].set_active(True)

    def _on_btn_clicked(self, index: int):
        self.set_current_index(index)
        self.page_changed.emit(index)

    def set_current_index(self, index: int):
        for idx, btn in enumerate(self._buttons):
            btn.set_active(idx == index)
