"""Verification page view for executing and inspecting KiCad quality gates."""

from pathlib import Path
import subprocess
import sys
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from tools.gui import icons, theme
from tools.gui.services.process_runner import ProcessRunner
from tools.gui.state import AppState
from tools.gui.widgets.status_pill import StatusPill

GATES = [
    ("erc", "Schematic ERC", "required"),
    ("drc", "PCB Design Rules", "required"),
    ("schematic_parity", "Schematic Parity", "required"),
    ("library_references", "Library Tables & References", "required"),
    ("portability", "Path Portability & Variables", "required"),
    ("footprint_assignment", "Footprint Assignments", "required"),
    ("pin_pad_mapping", "Symbol Pin / Footprint Pad", "required"),
    ("component_metadata", "Manufacturer, MPN, Datasheet", "advisory"),
    ("models_3d", "3D Model Resolution", "advisory"),
    ("bom", "Approved Parts Records", "advisory"),
    ("firmware", "Firmware Unit Tests", "disabled"),
    ("thermal", "Thermal Dissipation Estimate", "disabled"),
]


class VerificationPage(QWidget):
    """View for running and visualizing quality verification gates."""

    def __init__(self, app_state: AppState, runner: ProcessRunner):
        super().__init__()
        self.app_state = app_state
        self.runner = runner
        self._last_report_dir: Optional[str] = None
        self._gate_data: Dict[str, Any] = {}

        self.app_state.active_project_changed.connect(self._on_active_project_changed)
        self.runner.finished.connect(self._on_run_finished)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header
        title_box = QVBoxLayout()
        h1 = QLabel("Quality Gate Verification")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("Run KiCad ERC, DRC, parity, portability, library resolution, and part metadata checks.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Top Control Card
        ctrl_card = QFrame()
        ctrl_card.setObjectName("card")
        ctrl_layout = QVBoxLayout(ctrl_card)

        proj_row = QHBoxLayout()
        self.proj_lbl = QLabel("Active Project: None")
        self.proj_lbl.setStyleSheet("font-weight: bold; font-size: 14px;")
        proj_row.addWidget(self.proj_lbl)

        self.overall_pill = StatusPill("READY")
        proj_row.addWidget(self.overall_pill)
        proj_row.addStretch()
        ctrl_layout.addLayout(proj_row)

        ctrl_row = QHBoxLayout()
        self.run_btn = QPushButton("Run Verification")
        self.run_btn.setIcon(icons.get_icon("play", "#ffffff", 14))
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._start_verification)
        ctrl_row.addWidget(self.run_btn)

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self.runner.cancel)
        ctrl_row.addWidget(self.cancel_btn)

        self.release_cb = QCheckBox("Release Mode (--release: all gates required)")
        ctrl_row.addWidget(self.release_cb)

        ctrl_row.addStretch()

        self.open_report_btn = QPushButton("Open Report Folder")
        self.open_report_btn.setIcon(icons.get_icon("folder", "#9ba1b0", 14))
        self.open_report_btn.setEnabled(False)
        self.open_report_btn.clicked.connect(self._open_report_dir)
        ctrl_row.addWidget(self.open_report_btn)

        ctrl_layout.addLayout(ctrl_row)

        self.progress = QProgressBar()
        self.progress.setVisible(False)
        self.progress.setRange(0, 0)
        ctrl_layout.addWidget(self.progress)

        main_layout.addWidget(ctrl_card)

        # Gates Table & Findings Split using interactive QSplitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: Gates Table
        table_card = QFrame()
        table_card.setObjectName("card")
        t_layout = QVBoxLayout(table_card)
        t_lbl = QLabel("Configured Verification Gates")
        t_lbl.setObjectName("h2")
        t_layout.addWidget(t_lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Status", "Gate Name", "Check Description"])
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 95)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_gate_selected)
        t_layout.addWidget(self.table)
        self.splitter.addWidget(table_card)

        # Right: Findings Card
        findings_card = QFrame()
        findings_card.setObjectName("card")
        f_layout = QVBoxLayout(findings_card)
        f_lbl = QLabel("Gate Findings & Exclusions")
        f_lbl.setObjectName("h2")
        f_layout.addWidget(f_lbl)

        self.findings_view = QPlainTextEdit()
        self.findings_view.setReadOnly(True)
        self.findings_view.setPlaceholderText("Select a gate from the left to view detailed findings or run verification.")
        f_layout.addWidget(self.findings_view)
        self.splitter.addWidget(findings_card)

        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([580, 420])

        main_layout.addWidget(self.splitter, 1)

        self._populate_initial_table()
        self._on_active_project_changed()

    def _populate_initial_table(self):
        self.table.setRowCount(len(GATES))
        for idx, (gid, title, severity) in enumerate(GATES):
            pill = StatusPill("READY", severity.upper())
            self.table.setCellWidget(idx, 0, pill)

            item_id = QTableWidgetItem(gid)
            item_id.setData(Qt.ItemDataRole.UserRole, gid)
            self.table.setItem(idx, 1, item_id)
            self.table.setItem(idx, 2, QTableWidgetItem(title))

    def _on_active_project_changed(self):
        p = self.app_state.active_project
        if p:
            self.proj_lbl.setText(f"Active Project: {p.name}")
            self.run_btn.setEnabled(True)
        else:
            self.proj_lbl.setText("Active Project: None (select one in Dashboard or Projects)")
            self.run_btn.setEnabled(False)

    def _start_verification(self):
        p = self.app_state.active_project
        if not p:
            return

        self.run_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.progress.setVisible(True)
        self.overall_pill.setStatus("WARN", "RUNNING")
        self.findings_view.setPlainText("Running quality verification gates with KiCad toolchain...")

        args = ["verify", str(p), "--json"]
        if self.release_cb.isChecked():
            args.append("--release")

        self.runner.start_kit_command(args, json_mode=True)

    def _on_run_finished(self, exit_code: int, raw_output: str, parsed_json: Optional[Any]):
        self.run_btn.setEnabled(True)
        self.cancel_btn.setEnabled(False)
        self.progress.setVisible(False)

        if not parsed_json or not isinstance(parsed_json, dict):
            self.overall_pill.setStatus("FAIL" if exit_code != 0 else "PASS")
            self.findings_view.setPlainText(raw_output)
            return

        qg = parsed_json.get("quality_gate", "FAIL")
        self.overall_pill.setStatus(qg)

        self._last_report_dir = parsed_json.get("report_dir")
        self.open_report_btn.setEnabled(bool(self._last_report_dir))

        self._gate_data = parsed_json.get("gates", {})
        for idx, (gid, _, _) in enumerate(GATES):
            gate_res = self._gate_data.get(gid, {})
            st = gate_res.get("status", "NOT_TESTED")
            pill = self.table.cellWidget(idx, 0)
            if isinstance(pill, StatusPill):
                pill.setStatus(st)

        summary_text = [
            f"Overall Quality Gate: {qg}",
            f"Exit Code: {exit_code}",
            f"Report Directory: {self._last_report_dir or 'None'}",
            f"Sources Unchanged: {parsed_json.get('sources_unchanged', True)}",
            "",
            "Select any gate in the table to inspect individual findings.",
        ]
        self.findings_view.setPlainText("\n".join(summary_text))

    def _on_gate_selected(self):
        row = self.table.currentRow()
        if row < 0:
            return
        gid = self.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
        data = self._gate_data.get(gid)

        if not data:
            self.findings_view.setPlainText(f"Gate: {gid}\nStatus: Not executed in current session.")
            return

        lines = [
            f"Gate: {gid}",
            f"Status: {data.get('status')}",
            f"Severity: {data.get('severity')}",
            "",
            "Findings:",
        ]
        findings = data.get("findings", [])
        if not findings:
            lines.append("  (No violations or findings reported)")
        else:
            for f in findings:
                if isinstance(f, dict):
                    lines.append(f"  • [{f.get('type', 'finding')}] {f.get('message', f.get('description', str(f)))}")
                else:
                    lines.append(f"  • {f}")

        exclusions = data.get("exclusions", [])
        if exclusions:
            lines.append("")
            lines.append("Exclusions:")
            for ex in exclusions:
                lines.append(f"  - {ex}")

        self.findings_view.setPlainText("\n".join(lines))

    def _open_report_dir(self):
        if self._last_report_dir and Path(self._last_report_dir).is_dir():
            if sys.platform == "darwin":
                subprocess.run(["open", self._last_report_dir])
            else:
                subprocess.run(["xdg-open", self._last_report_dir])
