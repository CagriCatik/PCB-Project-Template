"""Main application window uniting navigation sidebar, stacked pages, and output console."""

from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMainWindow,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from tools.gui.pages.dashboard_page import DashboardPage
from tools.gui.pages.manufacturing_page import ManufacturingPage
from tools.gui.pages.new_project_page import NewProjectPage
from tools.gui.pages.projects_page import ProjectsPage
from tools.gui.pages.settings_page import SettingsPage
from tools.gui.pages.verification_page import VerificationPage
from tools.gui.services.process_runner import ProcessRunner
from tools.gui.state import AppState
from tools.gui.widgets.console_drawer import ConsoleDrawer
from tools.gui.widgets.sidebar import Sidebar


class MainWindow(QMainWindow):
    """Main window of the PCB-Project-Template desktop GUI."""

    def __init__(self, app_state: AppState):
        super().__init__()
        self.app_state = app_state
        self.runner = ProcessRunner(self)
        self.settings = QSettings("PCB-Project-Template", "KitManager")

        self.setWindowTitle("PCB Project Kit – KiCad 10.0.7")
        self.resize(1120, 740)
        self.setMinimumSize(900, 580)

        # Central widget with horizontal layout (Sidebar | Content + Console Splitter)
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 1. Left Sidebar
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._on_navigate)
        root_layout.addWidget(self.sidebar)

        # 2. Right area (Stacked pages on top, Console drawer at bottom in a vertical QSplitter)
        self.stack = QStackedWidget()

        self.dashboard_page = DashboardPage(self.app_state)
        self.dashboard_page.navigate_to_page.connect(self._on_navigate)
        self.stack.addWidget(self.dashboard_page)  # index 0

        self.new_project_page = NewProjectPage(self.app_state)
        self.new_project_page.project_created.connect(self._on_project_created)
        self.stack.addWidget(self.new_project_page)  # index 1

        self.projects_page = ProjectsPage(self.app_state)
        self.stack.addWidget(self.projects_page)  # index 2

        self.verification_page = VerificationPage(self.app_state, self.runner)
        self.stack.addWidget(self.verification_page)  # index 3

        self.manufacturing_page = ManufacturingPage(self.app_state, self.runner)
        self.stack.addWidget(self.manufacturing_page)  # index 4

        self.settings_page = SettingsPage(self.runner)
        self.stack.addWidget(self.settings_page)  # index 5

        # Console Drawer at bottom
        self.console = ConsoleDrawer()

        # Resizable vertical splitter between active page and output console
        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(self.stack)
        self.right_splitter.addWidget(self.console)
        self.right_splitter.setCollapsible(0, False)
        self.right_splitter.setCollapsible(1, False)
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 0)
        self.right_splitter.setSizes([1000, 38])
        root_layout.addWidget(self.right_splitter, 1)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("KiCad 10.0.7 Toolchain Ready")

        # Connect Console Drawer and Process Runner
        self.console.collapsed_changed.connect(self._on_console_collapsed)
        self.runner.started.connect(self._on_process_started)
        self.runner.output_received.connect(self.console.append_output)
        self.runner.error_received.connect(self.console.append_error)
        self.runner.finished.connect(self._on_process_finished)

        self.app_state.active_project_changed.connect(self._update_status_bar)
        self._update_status_bar()

    def _on_console_collapsed(self, collapsed: bool):
        sizes = self.right_splitter.sizes()
        total = sum(sizes)
        if collapsed:
            self.right_splitter.setSizes([total - 38, 38])
        else:
            target_console = max(180, int(total * 0.28))
            self.right_splitter.setSizes([total - target_console, target_console])

    def _on_navigate(self, index: int):
        self.stack.setCurrentIndex(index)
        self.sidebar.set_current_index(index)

    def _on_project_created(self, path: str):
        self._on_navigate(0)  # Return to dashboard with new active project

    def _on_process_started(self):
        auto_open = self.settings.value("auto_open_console", True, type=bool)
        if auto_open:
            self.console.set_collapsed(False)
        self.console.set_running(True)
        self.status_bar.showMessage("Running process...")

    def _on_process_finished(self, exit_code: int, raw_output: str, parsed_json: Optional[object]):
        self.console.set_running(False)
        self.status_bar.showMessage(f"Process completed with exit code {exit_code}")

    def _update_status_bar(self):
        info = self.app_state.active_project_info()
        if info["active"]:
            self.status_bar.showMessage(f"Active: {info['name']} ({info['path']}) · KiCad 10.0.7")
        else:
            self.status_bar.showMessage("No project active · KiCad 10.0.7")
