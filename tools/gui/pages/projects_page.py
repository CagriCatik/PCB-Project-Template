"""Projects management page view."""

from pathlib import Path
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tools.gui import icons, theme
from tools.gui.services.project_service import ProjectService
from tools.gui.state import AppState
from tools.gui.widgets.status_pill import StatusPill


class ProjectsPage(QWidget):
    """View for browsing, selecting, and launching registered board projects."""

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.app_state.active_project_changed.connect(self.refresh_table)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title
        title_box = QVBoxLayout()
        h1 = QLabel("Project Registry")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("Machine-local index of hardware projects generated or registered with this kit.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Table Card
        card = QFrame()
        card.setObjectName("card")
        card_layout = QVBoxLayout(card)

        # Table
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Status", "Project Name", "Template", "Files", "Path"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 95)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        card_layout.addWidget(self.table)

        # Actions toolbar
        toolbar = QHBoxLayout()

        self.set_active_btn = QPushButton("Set as Active")
        self.set_active_btn.setIcon(icons.get_icon("check", "#ffffff", 14))
        self.set_active_btn.setObjectName("primary")
        self.set_active_btn.clicked.connect(self._set_selected_active)
        toolbar.addWidget(self.set_active_btn)

        self.open_kicad_btn = QPushButton("Open in KiCad")
        self.open_kicad_btn.setIcon(icons.get_icon("external_link", "#9ba1b0", 14))
        self.open_kicad_btn.clicked.connect(self._open_selected_kicad)
        toolbar.addWidget(self.open_kicad_btn)

        self.open_vscode_btn = QPushButton("Open in VS Code")
        self.open_vscode_btn.setIcon(icons.get_icon("code", "#9ba1b0", 14))
        self.open_vscode_btn.clicked.connect(self._open_selected_vscode)
        toolbar.addWidget(self.open_vscode_btn)

        self.reveal_btn = QPushButton("Reveal in Finder")
        self.reveal_btn.setIcon(icons.get_icon("folder", "#9ba1b0", 14))
        self.reveal_btn.clicked.connect(self._reveal_selected)
        toolbar.addWidget(self.reveal_btn)

        toolbar.addStretch()

        self.add_btn = QPushButton("Add Existing...")
        self.add_btn.setIcon(icons.get_icon("plus", "#9ba1b0", 14))
        self.add_btn.clicked.connect(self._add_existing_project)
        toolbar.addWidget(self.add_btn)

        self.forget_btn = QPushButton("Forget")
        self.forget_btn.setIcon(icons.get_icon("trash", "#ef4444", 14))
        self.forget_btn.setStyleSheet("color: #ef4444;")
        self.forget_btn.clicked.connect(self._forget_selected)
        toolbar.addWidget(self.forget_btn)

        card_layout.addLayout(toolbar)
        main_layout.addWidget(card)

        self.refresh_table()

    def refresh_table(self):
        self.table.setRowCount(0)
        projects = ProjectService.list_projects()
        active_path = str(self.app_state.active_project) if self.app_state.active_project else None

        for row_idx, p in enumerate(projects):
            self.table.insertRow(row_idx)
            is_active = (p["path"] == active_path)

            # 0: Status Pill
            pill = StatusPill("READY" if is_active else ("PASS" if p.get("exists") else "FAIL"),
                              "ACTIVE" if is_active else ("FOUND" if p.get("exists") else "MISSING"))
            self.table.setCellWidget(row_idx, 0, pill)

            # 1: Name
            pro_file = p.get("project_file")
            name = pro_file.replace(".kicad_pro", "") if pro_file else Path(p["path"]).name
            item_name = QTableWidgetItem(name)
            item_name.setData(Qt.ItemDataRole.UserRole, p["path"])
            self.table.setItem(row_idx, 1, item_name)

            # 2: Template
            tpl = p.get("template") or "generic"
            self.table.setItem(row_idx, 2, QTableWidgetItem(tpl))

            # 3: Files Valid
            files_ok = "Valid" if p.get("project_file") else "Incomplete"
            self.table.setItem(row_idx, 3, QTableWidgetItem(files_ok))

            # 4: Path
            self.table.setItem(row_idx, 4, QTableWidgetItem(p["path"]))

        self._update_buttons(False)

    def _selected_path(self) -> Optional[str]:
        selected = self.table.selectedItems()
        if not selected:
            return None
        row = self.table.currentRow()
        name_item = self.table.item(row, 1)
        return name_item.data(Qt.ItemDataRole.UserRole) if name_item else None

    def _on_selection_changed(self):
        has_sel = self._selected_path() is not None
        self._update_buttons(has_sel)

    def _update_buttons(self, has_selection: bool):
        self.set_active_btn.setEnabled(has_selection)
        self.open_kicad_btn.setEnabled(has_selection)
        self.open_vscode_btn.setEnabled(has_selection)
        self.reveal_btn.setEnabled(has_selection)
        self.forget_btn.setEnabled(has_selection)

    def _set_selected_active(self):
        path = self._selected_path()
        if path:
            self.app_state.set_active_project(path)

    def _open_selected_kicad(self):
        path = self._selected_path()
        if path:
            try:
                ProjectService.open_in_kicad(path)
            except Exception as e:
                QMessageBox.warning(self, "Open in KiCad Failed", str(e))

    def _open_selected_vscode(self):
        path = self._selected_path()
        if path:
            try:
                ProjectService.open_in_vscode(path)
            except Exception as e:
                QMessageBox.warning(self, "Open in VS Code Failed", str(e))

    def _reveal_selected(self):
        path = self._selected_path()
        if path:
            if sys.platform == "darwin":
                subprocess.run(["open", "-R", path])
            else:
                subprocess.run(["xdg-open", path])

    def _add_existing_project(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select KiCad Project Folder")
        if dir_path:
            try:
                ProjectService.register_project(dir_path)
                self.app_state.set_active_project(dir_path)
                self.refresh_table()
            except Exception as exc:
                QMessageBox.warning(self, "Invalid Project", f"Could not register project:\n{exc}")

    def _forget_selected(self):
        path = self._selected_path()
        if path:
            ProjectService.forget_project(path)
            if self.app_state.active_project and str(self.app_state.active_project) == path:
                self.app_state.set_active_project(None)
            self.refresh_table()
