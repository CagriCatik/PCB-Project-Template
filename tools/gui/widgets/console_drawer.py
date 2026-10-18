"""Collapsible process output console drawer."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from tools.gui import icons, theme


class ConsoleDrawer(QFrame):
    """Collapsible console drawer for live subprocess logging."""

    collapsed_changed = Signal(bool)

    def __init__(self):
        super().__init__()
        self._is_collapsed = True
        self.setFixedHeight(38)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 8)
        layout.setSpacing(6)

        # Header bar
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)

        self.title_label = QLabel("Output Console")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 12px; color: #a1a1aa;")
        header.addWidget(self.title_label)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 11px; color: #3b82f6;")
        header.addWidget(self.status_label)

        header.addStretch()

        self.autoscroll_cb = QCheckBox("Auto-scroll")
        self.autoscroll_cb.setChecked(True)
        self.autoscroll_cb.setStyleSheet("font-size: 11px; color: #a1a1aa;")
        header.addWidget(self.autoscroll_cb)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setIcon(icons.get_icon("trash", "#9ba1b0", 12))
        self.clear_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.clear_btn.clicked.connect(self.clear)
        header.addWidget(self.clear_btn)

        self.toggle_btn = QPushButton("Expand")
        self.toggle_btn.setIcon(icons.get_icon("chevron_up", "#9ba1b0", 12))
        self.toggle_btn.setStyleSheet("padding: 2px 8px; font-size: 11px;")
        self.toggle_btn.clicked.connect(self.toggle_collapsed)
        header.addWidget(self.toggle_btn)

        layout.addLayout(header)

        # Output text area
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setMaximumBlockCount(5000)
        self.text_edit.setVisible(False)
        self.text_edit.setMinimumHeight(80)
        layout.addWidget(self.text_edit)

        self.setStyleSheet(f"""
            ConsoleDrawer {{
                background-color: {theme.COLOR_BG_SURFACE};
                border-top: 1px solid {theme.COLOR_BORDER};
            }}
        """)

    def set_running(self, running: bool, task_name: str = ""):
        if running:
            self.status_label.setText(f"Running: {task_name}" if task_name else "Running...")
            self.status_label.setStyleSheet("color: #3b82f6; font-weight: bold;")
            if self._is_collapsed:
                self.set_collapsed(False)
        else:
            self.status_label.setText("Finished")
            self.status_label.setStyleSheet("color: #10b981;")

    def append_output(self, text: str):
        self._append(text, "#e4e4e7")

    def append_error(self, text: str):
        self._append(text, "#f87171")

    def _append(self, text: str, color_hex: str):
        cursor = self.text_edit.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color_hex))
        cursor.insertText(text, fmt)

        if self.autoscroll_cb.isChecked():
            self.text_edit.setTextCursor(cursor)
            self.text_edit.ensureCursorVisible()

    def clear(self):
        self.text_edit.clear()

    def toggle_collapsed(self):
        self.set_collapsed(not self._is_collapsed)

    def set_collapsed(self, collapsed: bool):
        self._is_collapsed = collapsed
        self.text_edit.setVisible(not collapsed)
        if collapsed:
            self.setFixedHeight(38)
        else:
            self.setMinimumHeight(120)
            self.setMaximumHeight(16777215)
        self.toggle_btn.setText("Expand" if collapsed else "Collapse")
        self.toggle_btn.setIcon(icons.get_icon("chevron_up" if collapsed else "chevron_down", "#9ba1b0", 12))
        self.collapsed_changed.emit(collapsed)
