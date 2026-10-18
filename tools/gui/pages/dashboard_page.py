"""Dashboard page view showing environment summary, active project, and quick actions."""

from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tools.gui import icons, theme
from tools.gui.services.project_service import ProjectService
from tools.gui.state import AppState
from tools.gui.widgets.status_pill import StatusPill


class DashboardPage(QWidget):
    """Primary overview dashboard."""

    navigate_to_page = Signal(int)  # 1: New Project, 2: Projects, 3: Verification, 4: Manufacturing

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.app_state.active_project_changed.connect(self.refresh_project)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title
        title_box = QVBoxLayout()
        h1 = QLabel("Engineering Dashboard")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("KiCad 10.0.7 Hardware & Firmware Project Workspace")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content_widget = QWidget()
        self.content_layout = QVBoxLayout(content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(16)

        # 1. Environment status banner card
        self._build_environment_card()

        # 2. Active project card
        self._build_active_project_card()

        # 3. Quick action buttons card
        self._build_quick_actions_card()

        # 4. Registered projects overview
        self._build_recent_projects_card()

        self.content_layout.addStretch()
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)

        self.refresh_project()

    def _build_environment_card(self):
        card = QFrame()
        card.setObjectName("card")
        layout = QHBoxLayout(card)

        info = ProjectService.get_environment_info()
        version = info.get("kicad_version") or "Not Found"
        is_exact = version == "10.0.7"

        status_pill = StatusPill("PASS" if is_exact else "WARN", f"KiCad {version}")
        layout.addWidget(status_pill)

        details = QVBoxLayout()
        lbl = QLabel("Toolchain Environment: KiCad 10.0.7 reference")
        lbl.setStyleSheet("font-weight: 600; font-size: 13px;")
        details.addWidget(lbl)
        cli_lbl = QLabel(f"CLI: {info.get('kicad_cli') or 'Missing'}   ·   Python venv: {info.get('kit_python') or 'Missing'}")
        cli_lbl.setObjectName("muted")
        cli_lbl.setWordWrap(True)
        details.addWidget(cli_lbl)
        layout.addLayout(details, 1)

        self.content_layout.addWidget(card)

    def _build_active_project_card(self):
        self.proj_card = QFrame()
        self.proj_card.setObjectName("card")
        layout = QVBoxLayout(self.proj_card)
        layout.setSpacing(10)

        hdr = QHBoxLayout()
        hdr_lbl = QLabel("Active Project Workspace")
        hdr_lbl.setObjectName("h2")
        hdr.addWidget(hdr_lbl)

        self.proj_badge = StatusPill("READY")
        hdr.addWidget(self.proj_badge)
        hdr.addStretch()
        layout.addLayout(hdr)

        self.proj_name_lbl = QLabel("No project selected")
        self.proj_name_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f4f4f6; margin-top: 2px;")
        layout.addWidget(self.proj_name_lbl)

        self.proj_path_lbl = QLabel("Select or create a project to begin.")
        self.proj_path_lbl.setObjectName("code")
        self.proj_path_lbl.setWordWrap(True)
        layout.addWidget(self.proj_path_lbl)

        # Quick action row for this project
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self.open_kicad_btn = QPushButton("Open in KiCad")
        self.open_kicad_btn.setIcon(icons.get_icon("external_link", "#9ba1b0", 14))
        self.open_kicad_btn.clicked.connect(self._open_kicad)
        btn_row.addWidget(self.open_kicad_btn)

        self.open_code_btn = QPushButton("Open in VS Code")
        self.open_code_btn.setIcon(icons.get_icon("code", "#9ba1b0", 14))
        self.open_code_btn.clicked.connect(self._open_vscode)
        btn_row.addWidget(self.open_code_btn)

        self.verify_btn = QPushButton("Run Verification")
        self.verify_btn.setIcon(icons.get_icon("shield_check", "#ffffff", 14))
        self.verify_btn.setObjectName("primary")
        self.verify_btn.clicked.connect(lambda: self.navigate_to_page.emit(3))
        btn_row.addWidget(self.verify_btn)

        self.export_btn = QPushButton("Manufacturing Export")
        self.export_btn.setIcon(icons.get_icon("package", "#9ba1b0", 14))
        self.export_btn.clicked.connect(lambda: self.navigate_to_page.emit(4))
        btn_row.addWidget(self.export_btn)

        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.content_layout.addWidget(self.proj_card)

    def _build_quick_actions_card(self):
        card = QFrame()
        card.setObjectName("card")
        layout = QVBoxLayout(card)
        layout.setSpacing(10)

        hdr = QLabel("Quick Actions")
        hdr.setObjectName("h2")
        layout.addWidget(hdr)

        row = QHBoxLayout()
        row.setSpacing(10)

        btn_new = QPushButton("New Board Project")
        btn_new.setIcon(icons.get_icon("plus", "#ffffff", 14))
        btn_new.setObjectName("primary")
        btn_new.clicked.connect(lambda: self.navigate_to_page.emit(1))
        row.addWidget(btn_new)

        btn_mgr = QPushButton("Manage Projects")
        btn_mgr.setIcon(icons.get_icon("folder", "#9ba1b0", 14))
        btn_mgr.clicked.connect(lambda: self.navigate_to_page.emit(2))
        row.addWidget(btn_mgr)

        btn_diag = QPushButton("Diagnostics && Settings")
        btn_diag.setIcon(icons.get_icon("settings", "#9ba1b0", 14))
        btn_diag.clicked.connect(lambda: self.navigate_to_page.emit(5))
        row.addWidget(btn_diag)

        row.addStretch()
        layout.addLayout(row)
        self.content_layout.addWidget(card)

    def _build_recent_projects_card(self):
        self.recent_card = QFrame()
        self.recent_card.setObjectName("card")
        self.recent_layout = QVBoxLayout(self.recent_card)
        self.recent_layout.setSpacing(10)

        hdr = QLabel("Registered Projects")
        hdr.setObjectName("h2")
        self.recent_layout.addWidget(hdr)

        self.projects_list_layout = QVBoxLayout()
        self.projects_list_layout.setSpacing(8)
        self.recent_layout.addLayout(self.projects_list_layout)

        self.content_layout.addWidget(self.recent_card)

    def _refresh_registered_list(self):
        # Clear previous
        while self.projects_list_layout.count():
            item = self.projects_list_layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.hide()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                sub_layout = item.layout()
                while sub_layout.count():
                    sub = sub_layout.takeAt(0)
                    if sub.widget():
                        sw = sub.widget()
                        sw.hide()
                        sw.setParent(None)
                        sw.deleteLater()

        projects = ProjectService.list_projects()
        if not projects:
            empty = QLabel("No registered projects found. Create or add one to get started.")
            empty.setObjectName("muted")
            self.projects_list_layout.addWidget(empty)
            return

        for p in projects[:5]:
            row = QHBoxLayout()
            row.setSpacing(10)
            from pathlib import Path
            pro = p.get("project_file")
            name = pro.replace(".kicad_pro", "") if pro else Path(p["path"]).name
            btn = QPushButton(f"{name}   ·   {p['path']}")
            btn.setIcon(icons.get_icon("folder", "#3b82f6", 14))
            btn.setStyleSheet("""
                QPushButton {
                    text-align: left;
                    padding: 8px 12px;
                    background-color: #12141a;
                    border: 1px solid #282d3b;
                    border-radius: 6px;
                    color: #f4f4f6;
                    font-size: 13px;
                }
                QPushButton:hover {
                    background-color: #1a1e27;
                    border-color: #3b82f6;
                }
            """)
            btn.clicked.connect(lambda checked=False, path=p["path"]: self._select_project(path))
            row.addWidget(btn, 1)

            pill = StatusPill("PASS" if p.get("exists") else "FAIL", "Ready" if p.get("exists") else "Missing")
            row.addWidget(pill)

            self.projects_list_layout.addLayout(row)

    def _select_project(self, path: str):
        self.app_state.set_active_project(path)

    def _open_kicad(self):
        p = self.app_state.active_project
        if p:
            try:
                ProjectService.open_in_kicad(str(p))
            except Exception as e:
                self.proj_path_lbl.setText(f"Error opening in KiCad: {e}")

    def _open_vscode(self):
        p = self.app_state.active_project
        if p:
            try:
                ProjectService.open_in_vscode(str(p))
            except Exception as e:
                self.proj_path_lbl.setText(f"Error opening in VS Code: {e}")

    def refresh_project(self):
        info = self.app_state.active_project_info()
        active = info["active"]

        self.open_kicad_btn.setEnabled(active)
        self.open_code_btn.setEnabled(active)
        self.verify_btn.setEnabled(active)
        self.export_btn.setEnabled(active)

        if active:
            self.proj_name_lbl.setText(info["name"])
            self.proj_path_lbl.setText(f"Path: {info['path']}  ·  File: {info['pro_file'] or 'None'}")
            self.proj_badge.setStatus("READY", info.get("template") or "KiCad Board")
        else:
            self.proj_name_lbl.setText("No project selected")
            self.proj_path_lbl.setText("Select a registered project from below or create a new project.")
            self.proj_badge.setStatus("DISABLED", "No Project")

        self._refresh_registered_list()
