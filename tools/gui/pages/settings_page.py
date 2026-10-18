"""Settings and environment diagnostics page view."""

from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from tools.gui import icons, theme
from tools.gui.services.process_runner import ProcessRunner
from tools.gui.services.project_service import ProjectService
from tools.gui.widgets.status_pill import StatusPill
from tools.quality import firmware


class SettingsPage(QWidget):
    """View for inspecting detected tools and configuring GUI preferences."""

    def __init__(self, runner: ProcessRunner):
        super().__init__()
        self.runner = runner
        self.settings = QSettings("PCB-Project-Template", "KitManager")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title
        title_box = QVBoxLayout()
        h1 = QLabel("Settings & Environment")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("Detected toolchains, KiCad 10.0.7 integration, and desktop manager preferences.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Scroll Area for responsive vertical fitting
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # Toolchain Status Card
        tools_card = QFrame()
        tools_card.setObjectName("card")
        t_layout = QVBoxLayout(tools_card)
        t_layout.setSpacing(12)

        t_hdr = QHBoxLayout()
        h2 = QLabel("Detected Tools & Toolchains")
        h2.setObjectName("h2")
        t_hdr.addWidget(h2)
        t_hdr.addStretch()

        self.doctor_btn = QPushButton("Run Doctor Check")
        self.doctor_btn.setIcon(icons.get_icon("doctor", "#9ba1b0", 14))
        self.doctor_btn.clicked.connect(self._run_doctor)
        t_hdr.addWidget(self.doctor_btn)
        t_layout.addLayout(t_hdr)

        self.tools_grid = QVBoxLayout()
        self.tools_grid.setSpacing(8)
        t_layout.addLayout(self.tools_grid)
        content_layout.addWidget(tools_card)

        # Preferences Card
        pref_card = QFrame()
        pref_card.setObjectName("card")
        p_layout = QVBoxLayout(pref_card)
        p_layout.setSpacing(12)

        p_h2 = QLabel("Manager Preferences (QSettings)")
        p_h2.setObjectName("h2")
        p_layout.addWidget(p_h2)

        lbl_def_dir = QLabel("Default New Project Directory:")
        lbl_def_dir.setStyleSheet("font-weight: 500;")
        p_layout.addWidget(lbl_def_dir)

        p_row = QHBoxLayout()
        p_row.setSpacing(8)
        self.default_dir_edit = QLineEdit()
        saved_dir = self.settings.value("default_projects_dir", str(Path.home() / "Projects"))
        self.default_dir_edit.setText(saved_dir)
        self.default_dir_edit.textChanged.connect(self._save_default_dir)
        p_row.addWidget(self.default_dir_edit, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_dir)
        p_row.addWidget(browse_btn)
        p_layout.addLayout(p_row)

        self.open_console_cb = QCheckBox("Automatically expand output console on process start")
        saved_cb = self.settings.value("auto_open_console", True, type=bool)
        self.open_console_cb.setChecked(saved_cb)
        self.open_console_cb.toggled.connect(self._save_console_pref)
        p_layout.addWidget(self.open_console_cb)

        content_layout.addWidget(pref_card)
        content_layout.addStretch()

        scroll.setWidget(content)
        main_layout.addWidget(scroll)

        self.refresh_tools()

    def refresh_tools(self):
        while self.tools_grid.count():
            item = self.tools_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                while item.layout().count():
                    sub = item.layout().takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

        env = ProjectService.get_environment_info()
        stm = firmware.stm32_environment()

        # Format versions cleanly for compact status pills
        cmake_raw = stm.get("cmake")
        cmake_badge = "v" + cmake_raw.split()[-1] if cmake_raw else "Missing"

        ninja_raw = stm.get("ninja")
        ninja_badge = "v" + ninja_raw.split()[-1] if ninja_raw else "Missing"

        cubemx_ver = stm.get("stm32cubemx", {}).get("version")
        cubemx_badge = "v" + cubemx_ver.split()[-1] if cubemx_ver else "Optional"

        rows = [
            ("KiCad CLI", env.get("kicad_cli"), env.get("kicad_version") == "10.0.7", env.get("kicad_version")),
            ("KiCad App Bundle", env.get("kicad_app"), bool(env.get("kicad_app")), "Found" if env.get("kicad_app") else "Missing"),
            ("Python Kit Venv", env.get("kit_python"), bool(env.get("kit_python")), "Ready" if env.get("kit_python") else "Missing"),
            ("STM32CubeMX", stm.get("stm32cubemx", {}).get("path"), bool(stm.get("stm32cubemx", {}).get("path")), cubemx_badge),
            ("Arm GNU Toolchain", stm.get("arm_gnu_toolchain", {}).get("bin"), bool(stm.get("arm_gnu_toolchain", {}).get("bin")), "Available" if stm.get("arm_gnu_toolchain", {}).get("bin") else "Not on PATH"),
            ("CMake", cmake_raw, bool(cmake_raw), cmake_badge),
            ("Ninja", ninja_raw, bool(ninja_raw), ninja_badge),
        ]

        for name, path_val, is_ok, badge_text in rows:
            h = QHBoxLayout()
            h.setSpacing(12)
            pill = StatusPill("PASS" if is_ok else "SKIPPED", badge_text or "Status")
            pill.setFixedWidth(90)
            h.addWidget(pill)

            lbl_name = QLabel(name)
            lbl_name.setStyleSheet("font-weight: 600;")
            lbl_name.setFixedWidth(160)
            h.addWidget(lbl_name)

            lbl_val = QLabel(str(path_val or "Not configured / Not found"))
            lbl_val.setObjectName("muted")
            lbl_val.setWordWrap(True)
            h.addWidget(lbl_val, 1)

            self.tools_grid.addLayout(h)

    def _browse_dir(self):
        chosen = QFileDialog.getExistingDirectory(self, "Select Default Projects Directory", self.default_dir_edit.text())
        if chosen:
            self.default_dir_edit.setText(chosen)

    def _save_default_dir(self, text: str):
        self.settings.setValue("default_projects_dir", text.strip())

    def _save_console_pref(self, checked: bool):
        self.settings.setValue("auto_open_console", checked)

    def _run_doctor(self):
        self.runner.start_kit_command(["doctor"])
