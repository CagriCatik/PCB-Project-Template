"""QApplication factory and bootstrap utilities."""

import os
import sys
from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from tools.gui import theme


def create_qapplication(argv: Optional[List[str]] = None, offscreen: bool = False) -> QApplication:
    """Create and configure the QApplication instance with appropriate metadata and theme."""
    if offscreen or os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    existing = QApplication.instance()
    if existing:
        return existing

    app = QApplication(argv or sys.argv[:1])
    app.setOrganizationName("PCB-Project-Template")
    app.setApplicationName("PCB Project Kit")
    app.setApplicationVersion("2.0.0")

    theme.apply_theme(app)
    return app
