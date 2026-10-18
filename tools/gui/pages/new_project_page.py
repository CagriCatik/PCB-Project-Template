"""New Project creation page view."""

from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from tools.gui.services.project_service import ProjectService
from tools.gui.state import AppState


class NewProjectPage(QWidget):
    """View for configuring and materializing a new KiCad board project."""

    project_created = Signal(str)  # emitted with new project path

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Title
        title_box = QVBoxLayout()
        h1 = QLabel("Create New Board Project")
        h1.setObjectName("h1")
        title_box.addWidget(h1)
        sub = QLabel("Instantiate an independent KiCad project with portable libraries and quality gates.")
        sub.setObjectName("muted")
        title_box.addWidget(sub)
        main_layout.addLayout(title_box)

        # Scroll Area for responsive vertical adaptation
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)

        # Form Card with clean maximum width constraint
        form_card = QFrame()
        form_card.setObjectName("card")
        form_card.setMaximumWidth(780)
        form_layout = QVBoxLayout(form_card)
        form_layout.setSpacing(10)

        # 1. Project Name
        lbl_name = QLabel("Project Name")
        lbl_name.setStyleSheet("font-weight: 600; font-size: 13px;")
        form_layout.addWidget(lbl_name)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("e.g. SensorHub-RevA")
        self.name_input.textChanged.connect(self._validate_form)
        form_layout.addWidget(self.name_input)

        self.name_hint = QLabel("Allowed: Letters, digits, spaces, '.', '-', '_'. Cannot end with space or dot.")
        self.name_hint.setObjectName("muted")
        form_layout.addWidget(self.name_hint)

        # 2. Destination Directory
        lbl_dest = QLabel("Destination Directory")
        lbl_dest.setStyleSheet("font-weight: 600; font-size: 13px;")
        form_layout.addWidget(lbl_dest)

        dest_row = QHBoxLayout()
        dest_row.setSpacing(8)
        self.dest_input = QLineEdit()
        default_dir = str(Path.home() / "Projects")
        self.dest_input.setText(default_dir)
        self.dest_input.textChanged.connect(self._validate_form)
        dest_row.addWidget(self.dest_input, 1)

        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_destination)
        dest_row.addWidget(browse_btn)
        form_layout.addLayout(dest_row)

        self.dest_preview = QLabel(f"Target: {default_dir}/(name)")
        self.dest_preview.setObjectName("code")
        self.dest_preview.setWordWrap(True)
        form_layout.addWidget(self.dest_preview)

        # 3. Template Selection
        lbl_tpl = QLabel("Project Template")
        lbl_tpl.setStyleSheet("font-weight: 600; font-size: 13px;")
        form_layout.addWidget(lbl_tpl)

        self.template_combo = QComboBox()
        self.templates_data = ProjectService.get_templates()
        for t_id, data in self.templates_data.items():
            self.template_combo.addItem(f"{data.get('title', t_id)}  ({t_id})", t_id)
        self.template_combo.currentIndexChanged.connect(self._on_template_changed)
        form_layout.addWidget(self.template_combo)

        self.template_desc = QLabel("")
        self.template_desc.setObjectName("muted")
        self.template_desc.setWordWrap(True)
        form_layout.addWidget(self.template_desc)

        # 4. Profile Selection
        lbl_prof = QLabel("Board Layer Profile")
        lbl_prof.setStyleSheet("font-weight: 600; font-size: 13px;")
        form_layout.addWidget(lbl_prof)

        self.profile_combo = QComboBox()
        self.profiles_data = ProjectService.get_profiles()
        form_layout.addWidget(self.profile_combo)

        # 5. Git repository option
        self.git_cb = QCheckBox("Initialize Git repository (runs git init only; no commits)")
        self.git_cb.setChecked(False)
        form_layout.addWidget(self.git_cb)

        # 6. Status / Validation message
        self.msg_lbl = QLabel("")
        self.msg_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
        self.msg_lbl.setWordWrap(True)
        form_layout.addWidget(self.msg_lbl)

        # 7. Action Button
        btn_row = QHBoxLayout()
        self.create_btn = QPushButton("Create Board Project")
        self.create_btn.setIcon(icons.get_icon("plus", "#ffffff", 15))
        self.create_btn.setObjectName("primary")
        self.create_btn.setMinimumHeight(38)
        self.create_btn.setMinimumWidth(180)
        self.create_btn.clicked.connect(self._on_create_clicked)
        btn_row.addWidget(self.create_btn)
        btn_row.addStretch()
        form_layout.addLayout(btn_row)

        scroll_layout.addWidget(form_card)
        scroll_layout.addStretch()
        scroll.setWidget(scroll_content)
        main_layout.addWidget(scroll)

        # Select generic-pcb as initial default template if available
        default_idx = self.template_combo.findData("generic-pcb")
        if default_idx >= 0:
            self.template_combo.setCurrentIndex(default_idx)
        else:
            self._on_template_changed(0)
        self._validate_form()

    def _browse_destination(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Select Parent Directory", self.dest_input.text())
        if dir_path:
            self.dest_input.setText(dir_path)

    def _on_template_changed(self, index: int):
        t_id = self.template_combo.currentData()
        info = self.templates_data.get(t_id, {})
        self.template_desc.setText(info.get("description", ""))

        # Populate profile_combo with profiles supported by this template
        self.profile_combo.clear()
        supported = info.get("profiles", [])
        for p_id in supported:
            p_data = self.profiles_data.get(p_id, {})
            title = p_data.get("title", p_id)
            cu = p_data.get("copper_layers")
            label = f"{title} ({cu} Copper Layers)" if cu else title
            self.profile_combo.addItem(label, p_id)

    def _target_path(self) -> Path:
        name = self.name_input.text()
        parent_text = self.dest_input.text().strip()
        parent = Path(parent_text).expanduser() if parent_text else Path.cwd()
        return parent / name if name else parent

    def _validate_form(self) -> bool:
        name = self.name_input.text()
        target = self._target_path()
        self.dest_preview.setText(f"Target path: {target}")

        if not name:
            self.msg_lbl.setText("Enter a project name to begin.")
            self.msg_lbl.setStyleSheet("color: #9ba1b0;")
            self.create_btn.setEnabled(False)
            return False

        valid, error = ProjectService.validate_new_project_input(name, str(target))
        if not valid:
            self.msg_lbl.setText(error)
            self.msg_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
            self.create_btn.setEnabled(False)
            return False

        self.msg_lbl.setText("Ready to materialize project.")
        self.msg_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
        self.create_btn.setEnabled(True)
        return True

    def _on_create_clicked(self):
        if not self._validate_form():
            return

        name = self.name_input.text()
        target = self._target_path()
        t_id = self.template_combo.currentData()
        p_id = self.profile_combo.currentData()
        git_init = self.git_cb.isChecked()

        try:
            self.create_btn.setEnabled(False)
            self.msg_lbl.setText("Creating project...")
            self.msg_lbl.setStyleSheet("color: #3b82f6;")

            path, record = ProjectService.create_project(
                template_id=t_id,
                dest=str(target),
                name=name,
                git=git_init,
                register=True,
                profile=p_id,
            )

            self.msg_lbl.setText(f"Project created successfully: {path}")
            self.msg_lbl.setStyleSheet("color: #10b981; font-weight: bold;")
            self.app_state.set_active_project(str(path))
            self.project_created.emit(str(path))

        except Exception as exc:
            self.msg_lbl.setText(f"Creation failed: {exc}")
            self.msg_lbl.setStyleSheet("color: #ef4444; font-weight: bold;")
        finally:
            self.create_btn.setEnabled(True)
