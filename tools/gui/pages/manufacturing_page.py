"""Manufacturing releases and export page view."""

from pathlib import Path
import subprocess
import sys
from typing import Any, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tools.gui import icons, theme
from tools.gui.services.process_runner import ProcessRunner
from tools.gui.services.project_service import ProjectService
from tools.gui.state import AppState
from tools.gui.widgets.status_pill import StatusPill


class ManufacturingPage(QWidget):
    """View for managing manufacturing exports, manifests, and release reproducibility."""

    def __init__(self, app_state: AppState, runner: ProcessRunner):
        super().__init__()
        self.app_state = app_state
        self.runner = runner
        self._last_export_dir: Optional[str] = None

        self.app_state.active_project_changed.connect(self._on_active_project_changed)
        self.runner.finished.connect(self._on_export_finished)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        title_box = QVBoxLayout()
        h1 = QLabel("Manufacturing Releases")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("Generate production drafts, inspect release status, and verify output reproducibility.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Control & Export Card
        export_card = QFrame()
        export_card.setObjectName("card")
        e_layout = QVBoxLayout(export_card)

        proj_row = QHBoxLayout()
        self.proj_lbl = QLabel("Active Project: None")
        self.proj_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        proj_row.addWidget(self.proj_lbl)
        proj_row.addStretch()
        e_layout.addLayout(proj_row)

        form_row = QHBoxLayout()
        rev_lbl = QLabel("Revision:")
        rev_lbl.setStyleSheet("font-weight: bold;")
        form_row.addWidget(rev_lbl)

        self.rev_input = QLineEdit("A1")
        self.rev_input.setFixedWidth(80)
        form_row.addWidget(self.rev_input)

        self.ibom_cb = QCheckBox("Generate Interactive HTML BOM (IBOM)")
        self.ibom_cb.setChecked(True)
        form_row.addWidget(self.ibom_cb)

        form_row.addSpacing(16)

        self.export_btn = QPushButton("Generate Draft Export (NO-GO)")
        self.export_btn.setIcon(icons.get_icon("package", "#ffffff", 14))
        self.export_btn.setObjectName("primary")
        self.export_btn.clicked.connect(self._start_export)
        form_row.addWidget(self.export_btn)

        self.open_folder_btn = QPushButton("Open Releases Folder")
        self.open_folder_btn.setIcon(icons.get_icon("folder", "#9ba1b0", 14))
        self.open_folder_btn.clicked.connect(self._open_releases_dir)
        form_row.addWidget(self.open_folder_btn)

        form_row.addStretch()
        e_layout.addLayout(form_row)
        main_layout.addWidget(export_card)

        # Releases Table & Manifest Details split using interactive QSplitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Releases Status Table
        table_card = QFrame()
        table_card.setObjectName("card")
        t_layout = QVBoxLayout(table_card)

        t_header = QHBoxLayout()
        t_lbl = QLabel("Existing Releases Status")
        t_lbl.setObjectName("h2")
        t_header.addWidget(t_lbl)
        t_header.addStretch()

        self.refresh_btn = QPushButton("Refresh Status")
        self.refresh_btn.setIcon(icons.get_icon("refresh", "#9ba1b0", 14))
        self.refresh_btn.clicked.connect(self.refresh_releases)
        t_header.addWidget(self.refresh_btn)
        t_layout.addLayout(t_header)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Status", "Release Label", "Details"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 95)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        t_layout.addWidget(self.table)
        self.splitter.addWidget(table_card)

        # Output / Manifest View
        details_card = QFrame()
        details_card.setObjectName("card")
        d_layout = QVBoxLayout(details_card)
        d_lbl = QLabel("Export Manifest & Designators")
        d_lbl.setObjectName("h2")
        d_layout.addWidget(d_lbl)

        self.details_view = QPlainTextEdit()
        self.details_view.setReadOnly(True)
        self.details_view.setPlaceholderText("Export outputs and manifest details will appear here.")
        d_layout.addWidget(self.details_view)
        self.splitter.addWidget(details_card)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([560, 440])

        main_layout.addWidget(self.splitter, 1)
        self._on_active_project_changed()

    def _on_active_project_changed(self):
        p = self.app_state.active_project
        if p:
            self.proj_lbl.setText(f"Active Project: {p.name}")
            self.export_btn.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.refresh_releases()
        else:
            self.proj_lbl.setText("Active Project: None (select one in Dashboard or Projects)")
            self.export_btn.setEnabled(False)
            self.refresh_btn.setEnabled(False)
            self.table.setRowCount(0)

    def refresh_releases(self):
        p = self.app_state.active_project
        if not p:
            return

        self.table.setRowCount(0)
        rows = ProjectService.get_release_status(str(p))
        for idx, r in enumerate(rows):
            self.table.insertRow(idx)

            st = r.get("status", "INCOMPLETE")
            pill = StatusPill(st)
            self.table.setCellWidget(idx, 0, pill)
            self.table.setItem(idx, 1, QTableWidgetItem(r.get("release", "")))
            self.table.setItem(idx, 2, QTableWidgetItem(r.get("detail", "")))

    def _start_export(self):
        p = self.app_state.active_project
        if not p:
            return

        rev = self.rev_input.text().strip() or "A1"
        args = ["export", str(p), "--revision", rev, "--json"]
        if not self.ibom_cb.isChecked():
            args.append("--no-ibom")

        self.export_btn.setEnabled(False)
        self.details_view.setPlainText(f"Generating draft export for revision {rev}...")
        self.runner.start_kit_command(args, json_mode=True)

    def _on_export_finished(self, exit_code: int, raw_output: str, parsed_json: Optional[Any]):
        self.export_btn.setEnabled(True)
        self.refresh_releases()

        if not parsed_json or not isinstance(parsed_json, dict):
            self.details_view.setPlainText(raw_output)
            return

        target_dir = parsed_json.get("directory", "")
        manifest = parsed_json.get("manifest", {})
        self._last_export_dir = target_dir

        lines = [
            f"Release Label: {manifest.get('label', 'Draft')}",
            f"Destination: {target_dir}",
            f"Quality Gate: {manifest.get('quality_gate', 'Unknown')}",
            "",
            "Generated Artifacts:",
        ]
        outputs = manifest.get("outputs", {})
        for name, path in outputs.items():
            lines.append(f"  • {name:20s}: {path}")

        findings = manifest.get("designator_findings", [])
        if findings:
            lines.append("")
            lines.append("Designator Consistency Findings:")
            for f in findings:
                lines.append(f"  ! {f.get('problem')}: {f.get('reference', '')}")

        self.details_view.setPlainText("\n".join(lines))

    def _open_releases_dir(self):
        p = self.app_state.active_project
        if not p:
            return
        rel_dir = p / "manufacturing/releases/generated"
        target = rel_dir if rel_dir.is_dir() else (p / "manufacturing")
        if sys.platform == "darwin":
            subprocess.run(["open", str(target)])
        else:
            subprocess.run(["xdg-open", str(target)])
