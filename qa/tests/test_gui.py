"""Automated unit, integration, and UI component tests for the PySide6 Desktop GUI."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from kit_test_support import FIXTURE, ROOT, TempDirTest
from tools.core.common import KitError

# Ensure offscreen platform before importing any Qt modules
os.environ["QT_QPA_PLATFORM"] = "offscreen"


class GuiModuleBoundaryTests(unittest.TestCase):
    """Test that core and backend packages never import PySide6 or GUI modules."""

    def test_core_packages_never_import_pyside_or_gui(self):
        core_packages = ["core", "kicad", "project", "quality", "release", "environment", "thermal", "plugins"]
        for pkg in core_packages:
            pkg_dir = ROOT / "tools" / pkg
            for py_file in pkg_dir.rglob("*.py"):
                content = py_file.read_text(errors="replace")
                self.assertNotIn("PySide6", content, f"{py_file} must not import PySide6")
                self.assertNotIn("tools.gui", content, f"{py_file} must not import tools.gui")

    def test_cli_handles_missing_pyside6_gracefully(self):
        from tools.cli.main import build_parser, run_command

        parser = build_parser()
        args = parser.parse_args(["gui"])

        with patch.dict(sys.modules, {"PySide6": None, "tools.gui.main": None}):
            with patch("builtins.__import__", side_effect=ImportError("No module named 'PySide6'")):
                with self.assertRaises(KitError) as ctx:
                    run_command(args)
                self.assertEqual(ctx.exception.exit_code, 2)
                self.assertIn("PySide6 is not installed", str(ctx.exception))
                self.assertIn("requirements-gui.txt", str(ctx.exception))

    def test_cli_gui_argument_registration(self):
        from tools.cli.main import build_parser

        parser = build_parser()
        args = parser.parse_args(["gui", "--project", "/tmp/my-board"])
        self.assertEqual(args.command, "gui")
        self.assertEqual(args.project, "/tmp/my-board")


class GuiValidationAndServiceTests(TempDirTest):
    """Test project service, form validation, and path handling."""

    def test_project_name_validation(self):
        from tools.gui.services.project_service import ProjectService

        valid, _ = ProjectService.validate_new_project_input("Valid-Project_1", str(self.tmp / "p1"))
        self.assertTrue(valid)

        # Spaces allowed in name
        valid, _ = ProjectService.validate_new_project_input("Project Name With Spaces", str(self.tmp / "p2"))
        self.assertTrue(valid)

        # Empty name
        valid, err = ProjectService.validate_new_project_input("", str(self.tmp / "p3"))
        self.assertFalse(valid)
        self.assertIn("empty", err.lower())

        # Ends with period
        valid, err = ProjectService.validate_new_project_input("Invalid.", str(self.tmp / "p4"))
        self.assertFalse(valid)

        # Ends with space
        valid, err = ProjectService.validate_new_project_input("Invalid ", str(self.tmp / "p5"))
        self.assertFalse(valid)

        # Too long (>80 chars)
        valid, err = ProjectService.validate_new_project_input("A" * 81, str(self.tmp / "p6"))
        self.assertFalse(valid)

        # Invalid start character
        valid, err = ProjectService.validate_new_project_input("-Invalid", str(self.tmp / "p7"))
        self.assertFalse(valid)

    def test_destination_directory_validation(self):
        from tools.gui.services.project_service import ProjectService

        # Non-empty existing directory rejected
        non_empty = self.tmp / "occupied"
        non_empty.mkdir()
        (non_empty / "file.txt").write_text("data")
        valid, err = ProjectService.validate_new_project_input("NewProject", str(non_empty))
        self.assertFalse(valid)
        self.assertIn("not an empty directory", err)

        # Existing regular file rejected
        file_path = self.tmp / "file.txt"
        file_path.write_text("data")
        valid, err = ProjectService.validate_new_project_input("NewProject", str(file_path))
        self.assertFalse(valid)
        self.assertIn("existing file", err)

        # Empty string rejected
        valid, err = ProjectService.validate_new_project_input("NewProject", "   ")
        self.assertFalse(valid)
        self.assertIn("empty", err.lower())

    def test_project_creation_with_unicode_and_spaces(self):
        from tools.gui.services.project_service import ProjectService

        target_dir = self.tmp / "Projekt Ordner 🚀 / Unterordner – Test"
        name = "Board-Project"
        dest = str(target_dir / name)

        path, record = ProjectService.create_project(
            template_id="generic-pcb",
            dest=dest,
            name=name,
            git=False,
            register=False,
            profile="2-layer",
        )

        self.assertTrue(path.is_dir())
        self.assertTrue((path / f"{name}.kicad_pro").is_file())
        self.assertEqual(record["template"], "generic-pcb")
        self.assertEqual(record["profile"], "2-layer")

    def test_project_service_environment_and_metadata(self):
        from tools.gui.services.project_service import ProjectService

        info = ProjectService.get_environment_info()
        self.assertIn("kicad_version", info)
        self.assertIn("kicad_cli", info)
        self.assertIn("kit_python", info)
        self.assertIn("template_dir", info)

        tpls = ProjectService.get_templates()
        self.assertIn("generic-pcb", tpls)
        self.assertIn("stm32-embedded", tpls)

        profs = ProjectService.get_profiles()
        self.assertIn("2-layer", profs)
        self.assertIn("4-layer", profs)

    def test_project_service_registry_operations(self):
        from tools.gui.services.project_service import ProjectService

        proj = self.fixture_copy("service_reg_test")
        ProjectService.register_project(str(proj))

        listed = ProjectService.list_projects()
        paths = [p["path"] for p in listed]
        self.assertIn(str(proj.resolve()), paths)

        ProjectService.forget_project(str(proj))
        listed_after = ProjectService.list_projects()
        paths_after = [p["path"] for p in listed_after]
        self.assertNotIn(str(proj.resolve()), paths_after)

    def test_project_service_release_status_on_fixture(self):
        from tools.gui.services.project_service import ProjectService

        proj = self.fixture_copy("release_status_test")
        status = ProjectService.get_release_status(str(proj))
        self.assertIsInstance(status, list)


class GuiBaseTest(TempDirTest):
    """Base class for Qt GUI tests with offscreen initialization and event pumping."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            import PySide6.QtWidgets  # noqa: F401
            cls.has_pyside6 = True
        except ImportError:
            cls.has_pyside6 = False

    def setUp(self):
        super().setUp()
        if not self.has_pyside6:
            self.skipTest("PySide6 is not installed")

        from tools.gui.application import create_qapplication
        from PySide6.QtCore import QCoreApplication

        self.app = create_qapplication(offscreen=True)
        QCoreApplication.processEvents()

    def process_events(self):
        from PySide6.QtCore import QCoreApplication
        QCoreApplication.processEvents()


class GuiStateTests(GuiBaseTest):
    """Test reactive AppState signal emissions and active project summary."""

    def test_app_state_signals_and_active_project(self):
        from tools.gui.state import AppState

        state = AppState()
        events = []
        state.active_project_changed.connect(lambda p: events.append(p))

        proj = self.fixture_copy("app_state_proj")
        state.set_active_project(str(proj))

        self.assertEqual(state.active_project, proj.resolve())
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0], str(proj.resolve()))

        # Setting identical path does not re-emit
        state.set_active_project(str(proj))
        self.assertEqual(len(events), 1)

        # Clearing active project
        state.set_active_project(None)
        self.assertIsNone(state.active_project)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[1], "")

    def test_app_state_project_info_structure(self):
        from tools.gui.state import AppState

        state = AppState()
        state.set_active_project(None)
        info_empty = state.active_project_info()
        self.assertFalse(info_empty["active"])
        self.assertEqual(info_empty["name"], "(No project selected)")

        proj = self.fixture_copy("app_state_info_proj")
        state.set_active_project(str(proj))
        info_active = state.active_project_info()
        self.assertTrue(info_active["active"])
        self.assertEqual(info_active["name"], "app_state_info_proj")
        self.assertEqual(info_active["path"], str(proj.resolve()))
        self.assertTrue(info_active["pro_file"].endswith(".kicad_pro"))


class GuiWidgetsTests(GuiBaseTest):
    """Test standalone UI widgets (StatusPill, Sidebar, ConsoleDrawer)."""

    def test_status_pill_all_statuses(self):
        from tools.gui.widgets.status_pill import StatusPill

        statuses = [
            ("PASS", "#10b981"),
            ("FAIL", "#ef4444"),
            ("WARN", "#f59e0b"),
            ("READY", "#3b82f6"),
            ("SKIPPED", "#71717a"),
            ("DISABLED", "#71717a"),
            ("STALE", "#f59e0b"),
        ]
        for st, expected_color in statuses:
            pill = StatusPill(st)
            self.assertEqual(pill.text().strip(), st)
            self.assertIn(expected_color, pill.styleSheet())

        # Test custom text override
        pill_custom = StatusPill("PASS", "PASSED CHECKS")
        self.assertEqual(pill_custom.text().strip(), "PASSED CHECKS")
        self.assertIn("#10b981", pill_custom.styleSheet())

    def test_sidebar_navigation_buttons(self):
        from tools.gui.widgets.sidebar import Sidebar

        sidebar = Sidebar()
        self.assertEqual(len(sidebar._buttons), 6)

        # Default active is 0
        self.assertTrue(sidebar._buttons[0].isChecked())
        self.assertFalse(sidebar._buttons[1].isChecked())

        received_pages = []
        sidebar.page_changed.connect(lambda idx: received_pages.append(idx))

        # Click page 2
        sidebar._buttons[2].click()
        self.process_events()
        self.assertIn(2, received_pages)
        self.assertTrue(sidebar._buttons[2].isChecked())
        self.assertFalse(sidebar._buttons[0].isChecked())

        # Programmatic index change
        sidebar.set_current_index(4)
        self.assertTrue(sidebar._buttons[4].isChecked())
        self.assertFalse(sidebar._buttons[2].isChecked())

    def test_console_drawer_collapse_and_logging(self):
        from tools.gui.widgets.console_drawer import ConsoleDrawer

        drawer = ConsoleDrawer()
        self.assertTrue(drawer._is_collapsed)
        self.assertTrue(drawer.text_edit.isHidden())

        # Toggle expand
        drawer.toggle_collapsed()
        self.assertFalse(drawer._is_collapsed)
        self.assertFalse(drawer.text_edit.isHidden())

        # Test output logging
        drawer.append_output("Normal stdout message\n")
        drawer.append_error("Error stderr message\n")
        content = drawer.text_edit.toPlainText()
        self.assertIn("Normal stdout message", content)
        self.assertIn("Error stderr message", content)

        # Clear
        drawer.clear()
        self.assertEqual(drawer.text_edit.toPlainText(), "")

        # Test running status
        drawer.set_running(True, "Verification")
        self.assertIn("Running: Verification", drawer.status_label.text())
        drawer.set_running(False)
        self.assertEqual(drawer.status_label.text(), "Finished")

    def test_theme_application(self):
        from tools.gui import theme

        theme.apply_theme(self.app)
        self.assertIsNotNone(self.app.styleSheet())
        self.assertIn("Helvetica Neue", self.app.font().family())


class GuiDashboardPageTests(GuiBaseTest):
    """Test Engineering Dashboard page cards, bindings, and action signals."""

    def test_dashboard_without_active_project(self):
        from tools.gui.pages.dashboard_page import DashboardPage
        from tools.gui.state import AppState

        state = AppState()
        state.set_active_project(None)
        page = DashboardPage(state)

        self.assertEqual(page.proj_name_lbl.text(), "No project selected")
        self.assertFalse(page.open_kicad_btn.isEnabled())
        self.assertFalse(page.open_code_btn.isEnabled())
        self.assertFalse(page.verify_btn.isEnabled())
        self.assertFalse(page.export_btn.isEnabled())

    def test_dashboard_with_active_project(self):
        from tools.gui.pages.dashboard_page import DashboardPage
        from tools.gui.state import AppState

        proj = self.fixture_copy("dash_proj")
        state = AppState()
        state.set_active_project(str(proj))
        page = DashboardPage(state)

        self.assertEqual(page.proj_name_lbl.text(), "dash_proj")
        self.assertTrue(page.open_kicad_btn.isEnabled())
        self.assertTrue(page.open_code_btn.isEnabled())
        self.assertTrue(page.verify_btn.isEnabled())
        self.assertTrue(page.export_btn.isEnabled())

    def test_dashboard_quick_actions_signals(self):
        from tools.gui.pages.dashboard_page import DashboardPage
        from tools.gui.state import AppState

        state = AppState()
        proj = self.fixture_copy("dash_nav_proj")
        state.set_active_project(str(proj))
        page = DashboardPage(state)

        nav_events = []
        page.navigate_to_page.connect(lambda idx: nav_events.append(idx))

        page.verify_btn.click()
        self.process_events()
        self.assertEqual(nav_events[-1], 3)

        page.export_btn.click()
        self.process_events()
        self.assertEqual(nav_events[-1], 4)

    def test_dashboard_open_handlers(self):
        from tools.gui.pages.dashboard_page import DashboardPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState

        proj = self.fixture_copy("dash_open_proj")
        state = AppState()
        state.set_active_project(str(proj))
        page = DashboardPage(state)

        with patch.object(ProjectService, "open_in_kicad") as mock_kicad:
            page.open_kicad_btn.click()
            mock_kicad.assert_called_once_with(str(proj.resolve()))

        with patch.object(ProjectService, "open_in_vscode") as mock_code:
            page.open_code_btn.click()
            mock_code.assert_called_once_with(str(proj.resolve()))

        # Test error handling when launcher raises exception
        with patch.object(ProjectService, "open_in_kicad", side_effect=Exception("Failed to launch")):
            page.open_kicad_btn.click()
            self.assertIn("Failed to launch", page.proj_path_lbl.text())

    def test_dashboard_select_from_registered_list(self):
        from tools.gui.pages.dashboard_page import DashboardPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState
        from PySide6.QtWidgets import QPushButton

        proj = self.fixture_copy("dash_list_proj")
        ProjectService.register_project(str(proj))

        state = AppState()
        state.set_active_project(None)
        page = DashboardPage(state)

        # Find the button in projects_list_layout
        found_btn = None
        for i in range(page.projects_list_layout.count()):
            layout_item = page.projects_list_layout.itemAt(i)
            if layout_item and layout_item.layout():
                sub = layout_item.layout()
                for j in range(sub.count()):
                    w = sub.itemAt(j).widget()
                    if isinstance(w, QPushButton):
                        found_btn = w
                        break
            if found_btn:
                break

        self.assertIsNotNone(found_btn)
        found_btn.click()
        self.process_events()
        self.assertEqual(state.active_project, proj.resolve())


class GuiNewProjectPageTests(GuiBaseTest):
    """Test New Project creation page form inputs, validation, and execution."""

    def test_new_project_form_initial_state(self):
        from tools.gui.pages.new_project_page import NewProjectPage
        from tools.gui.state import AppState

        state = AppState()
        page = NewProjectPage(state)

        self.assertEqual(page.name_input.text(), "")
        self.assertGreater(page.template_combo.count(), 0)
        self.assertGreater(page.profile_combo.count(), 0)
        self.assertFalse(page.git_cb.isChecked())
        self.assertFalse(page.create_btn.isEnabled())

    def test_new_project_realtime_validation(self):
        from tools.gui.pages.new_project_page import NewProjectPage
        from tools.gui.state import AppState

        state = AppState()
        page = NewProjectPage(state)
        page.dest_input.setText(str(self.tmp))

        # Invalid name ending with space
        page.name_input.setText("TestProject ")
        self.process_events()
        self.assertFalse(page.create_btn.isEnabled())
        self.assertIn("space", page.msg_lbl.text().lower())

        # Valid name
        page.name_input.setText("ValidBoard-1")
        self.process_events()
        self.assertTrue(page.create_btn.isEnabled())
        self.assertIn("Ready to materialize", page.msg_lbl.text())

    def test_new_project_template_description_changes(self):
        from tools.gui.pages.new_project_page import NewProjectPage
        from tools.gui.state import AppState

        state = AppState()
        page = NewProjectPage(state)

        if page.template_combo.count() > 1:
            page.template_combo.setCurrentIndex(1)
            self.process_events()
            self.assertTrue(len(page.template_desc.text()) > 0)

    def test_new_project_creation_success(self):
        from tools.gui.pages.new_project_page import NewProjectPage
        from tools.gui.state import AppState

        state = AppState()
        page = NewProjectPage(state)
        created_paths = []
        page.project_created.connect(lambda p: created_paths.append(p))

        page.dest_input.setText(str(self.tmp))
        page.name_input.setText("CreatedBoard")
        self.process_events()
        self.assertTrue(page.create_btn.isEnabled())

        page.create_btn.click()
        self.process_events()

        self.assertEqual(len(created_paths), 1)
        expected_dir = self.tmp / "CreatedBoard"
        self.assertTrue(expected_dir.is_dir())
        self.assertTrue((expected_dir / "CreatedBoard.kicad_pro").is_file())
        self.assertEqual(state.active_project, expected_dir.resolve())
        self.assertIn("CreatedBoard", page.msg_lbl.text())

    def test_new_project_creation_failure_handled(self):
        from tools.gui.pages.new_project_page import NewProjectPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState

        state = AppState()
        page = NewProjectPage(state)
        page.dest_input.setText(str(self.tmp))
        page.name_input.setText("FailBoard")
        self.process_events()

        with patch.object(ProjectService, "create_project", side_effect=KitError("Template error")):
            page.create_btn.click()
            self.process_events()
            self.assertIn("Template error", page.msg_lbl.text())
            self.assertTrue(page.create_btn.isEnabled())


class GuiProjectsPageTests(GuiBaseTest):
    """Test Project Registry management page."""

    def test_projects_page_table_and_selection(self):
        from tools.gui.pages.projects_page import ProjectsPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState

        proj = self.fixture_copy("reg_table_proj")
        ProjectService.register_project(str(proj))

        state = AppState()
        page = ProjectsPage(state)

        self.assertGreater(page.table.rowCount(), 0)
        self.assertFalse(page.set_active_btn.isEnabled())
        self.assertFalse(page.open_kicad_btn.isEnabled())

        # Select first row
        page.table.selectRow(0)
        self.process_events()
        self.assertTrue(page.set_active_btn.isEnabled())
        self.assertTrue(page.open_kicad_btn.isEnabled())
        self.assertTrue(page.forget_btn.isEnabled())

    def test_projects_page_set_active_and_forget(self):
        from tools.gui.pages.projects_page import ProjectsPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState
        from PySide6.QtCore import Qt

        proj = self.fixture_copy("set_active_proj")
        ProjectService.register_project(str(proj))

        state = AppState()
        page = ProjectsPage(state)

        # Find row for this project by path stored in item data
        target_row = -1
        for row in range(page.table.rowCount()):
            item = page.table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == str(proj.resolve()):
                target_row = row
                break
        self.assertGreaterEqual(target_row, 0)

        page.table.selectRow(target_row)
        page.set_active_btn.click()
        self.process_events()
        self.assertEqual(state.active_project, proj.resolve())

        # Test Forget action
        page.table.selectRow(target_row)
        page.forget_btn.click()
        self.process_events()
        self.assertIsNone(state.active_project)

    def test_projects_page_add_existing_dialog(self):
        from tools.gui.pages.projects_page import ProjectsPage
        from tools.gui.state import AppState
        from PySide6.QtWidgets import QFileDialog, QMessageBox

        proj = self.fixture_copy("add_existing_proj")
        state = AppState()
        page = ProjectsPage(state)

        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(proj)):
            page.add_btn.click()
            self.process_events()
            self.assertEqual(state.active_project, proj.resolve())

        # Test invalid path shows warning dialog
        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(self.tmp / "nonexistent")):
            with patch.object(QMessageBox, "warning") as mock_warn:
                page.add_btn.click()
                self.process_events()
                mock_warn.assert_called_once()

    def test_projects_page_open_and_reveal_actions(self):
        from tools.gui.pages.projects_page import ProjectsPage
        from tools.gui.services.project_service import ProjectService
        from tools.gui.state import AppState
        from PySide6.QtCore import Qt

        proj = self.fixture_copy("open_reveal_proj")
        ProjectService.register_project(str(proj))

        state = AppState()
        page = ProjectsPage(state)

        # Select row
        target_row = -1
        for row in range(page.table.rowCount()):
            item = page.table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == str(proj.resolve()):
                target_row = row
                break
        self.assertGreaterEqual(target_row, 0)
        page.table.selectRow(target_row)

        with patch("subprocess.run") as mock_subp:
            page.reveal_btn.click()
            mock_subp.assert_called_once()

        with patch.object(ProjectService, "open_in_kicad") as mock_kicad:
            page.open_kicad_btn.click()
            mock_kicad.assert_called_once_with(str(proj.resolve()))

        with patch.object(ProjectService, "open_in_vscode") as mock_code:
            page.open_vscode_btn.click()
            mock_code.assert_called_once_with(str(proj.resolve()))


class GuiVerificationPageTests(GuiBaseTest):
    """Test Quality Gate Verification page runner integration and findings view."""

    def test_verification_page_initial_table(self):
        from tools.gui.pages.verification_page import VerificationPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = VerificationPage(state, runner)

        self.assertEqual(page.table.rowCount(), 12)
        # Check first gate
        self.assertEqual(page.table.item(0, 1).text(), "erc")
        self.assertFalse(page.run_btn.isEnabled())

    def test_verification_page_start_command(self):
        from tools.gui.pages.verification_page import VerificationPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        proj = self.fixture_copy("verify_cmd_proj")
        state = AppState()
        state.set_active_project(str(proj))
        runner = ProcessRunner()
        page = VerificationPage(state, runner)

        self.assertTrue(page.run_btn.isEnabled())

        with patch.object(runner, "start_kit_command") as mock_start:
            page.run_btn.click()
            self.process_events()
            mock_start.assert_called_once_with(["verify", str(proj.resolve()), "--json"], json_mode=True)
            self.assertFalse(page.run_btn.isEnabled())
            self.assertTrue(page.cancel_btn.isEnabled())
            self.assertFalse(page.progress.isHidden())

        # With --release checkbox checked
        with patch.object(runner, "start_kit_command") as mock_start_rel:
            page.release_cb.setChecked(True)
            page._start_verification()
            mock_start_rel.assert_called_once_with(
                ["verify", str(proj.resolve()), "--json", "--release"], json_mode=True
            )

    def test_verification_page_json_results_and_findings(self):
        from tools.gui.pages.verification_page import VerificationPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = VerificationPage(state, runner)

        mock_results = {
            "quality_gate": "PASS",
            "report_dir": str(self.tmp / "reports"),
            "sources_unchanged": True,
            "gates": {
                "erc": {"status": "PASS", "severity": "required", "findings": []},
                "drc": {
                    "status": "FAIL",
                    "severity": "required",
                    "findings": [{"type": "clearance", "message": "Track too close to pad"}],
                    "exclusions": ["ignored-1"],
                },
            },
        }

        page._on_run_finished(0, "", mock_results)
        self.process_events()

        self.assertEqual(page.overall_pill.text().strip(), "PASS")
        self.assertTrue(page.open_report_btn.isEnabled())
        self.assertEqual(page.table.cellWidget(0, 0).text().strip(), "PASS")
        self.assertEqual(page.table.cellWidget(1, 0).text().strip(), "FAIL")

        # Select DRC row to view findings
        page.table.selectRow(1)
        self.process_events()
        findings_text = page.findings_view.toPlainText()
        self.assertIn("Track too close to pad", findings_text)
        self.assertIn("ignored-1", findings_text)

    def test_verification_page_raw_error_handling(self):
        from tools.gui.pages.verification_page import VerificationPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = VerificationPage(state, runner)

        page._on_run_finished(1, "KiCad CLI encountered a segfault", None)
        self.process_events()
        self.assertEqual(page.overall_pill.text().strip(), "FAIL")
        self.assertIn("segfault", page.findings_view.toPlainText())

    def test_verification_page_open_report_and_cancel(self):
        from tools.gui.pages.verification_page import VerificationPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = VerificationPage(state, runner)

        rep_dir = self.tmp / "rep_dir"
        rep_dir.mkdir()
        page._last_report_dir = str(rep_dir)
        page.open_report_btn.setEnabled(True)

        with patch("subprocess.run") as mock_subp:
            page.open_report_btn.click()
            mock_subp.assert_called_once()

        with patch.object(runner, "cancel") as mock_cancel:
            page.cancel_btn.setEnabled(True)
            page.cancel_btn.click()
            mock_cancel.assert_called_once()


class GuiManufacturingPageTests(GuiBaseTest):
    """Test Manufacturing Releases page export triggers and manifest display."""

    def test_manufacturing_page_initial_and_active_state(self):
        from tools.gui.pages.manufacturing_page import ManufacturingPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = ManufacturingPage(state, runner)

        self.assertEqual(page.rev_input.text(), "A1")
        self.assertTrue(page.ibom_cb.isChecked())
        self.assertFalse(page.export_btn.isEnabled())

        proj = self.fixture_copy("mfg_active_proj")
        state.set_active_project(str(proj))
        self.process_events()
        self.assertTrue(page.export_btn.isEnabled())

    def test_manufacturing_page_start_export_arguments(self):
        from tools.gui.pages.manufacturing_page import ManufacturingPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        proj = self.fixture_copy("mfg_cmd_proj")
        state = AppState()
        state.set_active_project(str(proj))
        runner = ProcessRunner()
        page = ManufacturingPage(state, runner)

        with patch.object(runner, "start_kit_command") as mock_start:
            page.export_btn.click()
            mock_start.assert_called_once_with(
                ["export", str(proj.resolve()), "--revision", "A1", "--json"], json_mode=True
            )

        # With revision B2 and no ibom
        with patch.object(runner, "start_kit_command") as mock_start2:
            page.rev_input.setText("B2")
            page.ibom_cb.setChecked(False)
            page._start_export()
            mock_start2.assert_called_once_with(
                ["export", str(proj.resolve()), "--revision", "B2", "--json", "--no-ibom"], json_mode=True
            )

    def test_manufacturing_page_export_finished_json_parsing(self):
        from tools.gui.pages.manufacturing_page import ManufacturingPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        state = AppState()
        runner = ProcessRunner()
        page = ManufacturingPage(state, runner)

        mock_export = {
            "directory": str(self.tmp / "manufacturing/releases/generated/rev-A1-DRAFT"),
            "manifest": {
                "label": "rev-A1-DRAFT",
                "quality_gate": "PASS",
                "outputs": {
                    "gerbers": "gerbers.zip",
                    "bom": "bom.csv",
                },
                "designator_findings": [
                    {"problem": "Unplaced symbol", "reference": "R4"}
                ],
            },
        }

        page._on_export_finished(0, "", mock_export)
        self.process_events()

        details = page.details_view.toPlainText()
        self.assertIn("rev-A1-DRAFT", details)
        self.assertIn("gerbers.zip", details)
        self.assertIn("Unplaced symbol: R4", details)

    def test_manufacturing_page_open_releases_dir(self):
        from tools.gui.pages.manufacturing_page import ManufacturingPage
        from tools.gui.services.process_runner import ProcessRunner
        from tools.gui.state import AppState

        proj = self.fixture_copy("mfg_open_proj")
        rel_dir = proj / "manufacturing/releases/generated"
        rel_dir.mkdir(parents=True)

        state = AppState()
        state.set_active_project(str(proj))
        runner = ProcessRunner()
        page = ManufacturingPage(state, runner)

        with patch("subprocess.run") as mock_subp:
            page.open_folder_btn.click()
            mock_subp.assert_called_once()


class GuiSettingsPageTests(GuiBaseTest):
    """Test Settings & Diagnostics page tools inspection and preference saving."""

    def test_settings_page_tools_grid(self):
        from tools.gui.pages.settings_page import SettingsPage
        from tools.gui.services.process_runner import ProcessRunner

        runner = ProcessRunner()
        page = SettingsPage(runner)

        # Tools grid should contain rows
        self.assertGreater(page.tools_grid.count(), 0)

    def test_settings_page_preferences(self):
        from tools.gui.pages.settings_page import SettingsPage
        from tools.gui.services.process_runner import ProcessRunner

        runner = ProcessRunner()
        page = SettingsPage(runner)

        test_dir = str(self.tmp / "CustomProjects")
        page.default_dir_edit.setText(test_dir)
        self.process_events()
        self.assertEqual(page.settings.value("default_projects_dir"), test_dir)

        page.open_console_cb.setChecked(False)
        self.process_events()
        self.assertEqual(page.settings.value("auto_open_console", type=bool), False)

    def test_settings_page_doctor_command(self):
        from tools.gui.pages.settings_page import SettingsPage
        from tools.gui.services.process_runner import ProcessRunner

        runner = ProcessRunner()
        page = SettingsPage(runner)

        with patch.object(runner, "start_kit_command") as mock_start:
            page.doctor_btn.click()
            mock_start.assert_called_once_with(["doctor"])

    def test_settings_page_browse_directory(self):
        from tools.gui.pages.settings_page import SettingsPage
        from tools.gui.services.process_runner import ProcessRunner
        from PySide6.QtWidgets import QFileDialog

        runner = ProcessRunner()
        page = SettingsPage(runner)

        with patch.object(QFileDialog, "getExistingDirectory", return_value=str(self.tmp / "ChosenDir")):
            page._browse_dir()
            self.assertEqual(page.default_dir_edit.text(), str(self.tmp / "ChosenDir"))


class GuiMainWindowAndIntegrationTests(GuiBaseTest):
    """Test MainWindow page navigation, console integration, and end-to-end workflow."""

    def test_main_window_startup_and_navigation(self):
        from tools.gui.main_window import MainWindow
        from tools.gui.state import AppState

        state = AppState()
        window = MainWindow(state)

        # Check default layout
        self.assertEqual(window.stack.currentIndex(), 0)
        self.assertEqual(window.stack.count(), 6)

        # Navigate through pages
        for page_idx in range(6):
            window._on_navigate(page_idx)
            self.assertEqual(window.stack.currentIndex(), page_idx)
            self.assertEqual(window.sidebar._buttons[page_idx].isChecked(), True)

        # Check status bar message
        self.assertIn("KiCad 10.0.7", window.status_bar.currentMessage())

    def test_main_window_console_runner_integration(self):
        from tools.gui.main_window import MainWindow
        from tools.gui.state import AppState

        state = AppState()
        window = MainWindow(state)

        # Simulate process started
        window.runner.started.emit()
        self.process_events()
        self.assertFalse(window.console._is_collapsed)
        self.assertIn("Running process", window.status_bar.currentMessage())

        # Simulate stdout and stderr streaming
        window.runner.output_received.emit("Live build output line\n")
        window.runner.error_received.emit("Live build error line\n")
        self.process_events()
        console_text = window.console.text_edit.toPlainText()
        self.assertIn("Live build output line", console_text)
        self.assertIn("Live build error line", console_text)

        # Simulate process finished
        window.runner.finished.emit(0, "", None)
        self.process_events()
        self.assertIn("exit code 0", window.status_bar.currentMessage())

    def test_end_to_end_project_creation_and_routing(self):
        from tools.gui.main_window import MainWindow
        from tools.gui.state import AppState

        state = AppState()
        window = MainWindow(state)

        # Navigate to New Project page
        window._on_navigate(1)
        self.assertEqual(window.stack.currentIndex(), 1)

        # Fill out form and create project
        new_page = window.new_project_page
        new_page.dest_input.setText(str(self.tmp))
        new_page.name_input.setText("E2E-Board")
        self.process_events()
        self.assertTrue(new_page.create_btn.isEnabled())

        new_page.create_btn.click()
        self.process_events()

        # Should automatically route back to Dashboard (page 0)
        self.assertEqual(window.stack.currentIndex(), 0)
        self.assertIsNotNone(state.active_project)
        self.assertEqual(state.active_project.name, "E2E-Board")
        self.assertIn("E2E-Board", window.status_bar.currentMessage())


class GuiProcessRunnerRobustnessTests(GuiBaseTest):
    """Test async QProcess runner execution, line streaming, cancellation, and error handling."""

    def test_process_runner_real_command(self):
        from tools.gui.services.process_runner import ProcessRunner
        from PySide6.QtCore import QCoreApplication

        runner = ProcessRunner()
        results = []
        runner.finished.connect(lambda code, out, js: results.append((code, out, js)))

        runner.start_kit_command(["version"], json_mode=True)

        for _ in range(50):
            QCoreApplication.processEvents()
            if results:
                break
            runner._process.waitForFinished(100)

        self.assertTrue(len(results) > 0, "Command did not finish")
        code, out, parsed = results[0]
        self.assertEqual(code, 0)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("kit"), "2.0.0")

    def test_process_runner_cancel(self):
        from tools.gui.services.process_runner import ProcessRunner

        runner = ProcessRunner()
        cancelled = []
        runner.cancelled.connect(lambda: cancelled.append(True))

        runner.start_command(sys.executable, ["-c", "import time; time.sleep(10)"])
        self.assertTrue(runner.is_running())

        runner.cancel()
        self.assertFalse(runner.is_running())
        self.assertEqual(len(cancelled), 1)

    def test_process_runner_non_zero_exit(self):
        from tools.gui.services.process_runner import ProcessRunner
        from PySide6.QtCore import QCoreApplication

        runner = ProcessRunner()
        results = []
        runner.finished.connect(lambda code, out, js: results.append((code, out, js)))

        runner.start_command(sys.executable, ["-c", "import sys; sys.exit(42)"])

        for _ in range(50):
            QCoreApplication.processEvents()
            if results:
                break
            runner._process.waitForFinished(100)

        self.assertTrue(len(results) > 0)
        code, out, _ = results[0]
        self.assertEqual(code, 42)


class VectorIconTests(unittest.TestCase):
    """Test vector SVG icon rendering, caching, and absence of emojis."""

    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_icons_rendering_and_caching(self):
        from tools.gui import icons

        icon_names = ["dashboard", "plus", "folder", "shield_check", "package", "settings", "doctor", "play"]
        for name in icon_names:
            pix = icons.get_pixmap(name, "#3b82f6", 18)
            self.assertFalse(pix.isNull())
            self.assertEqual(pix.width() / pix.devicePixelRatio(), 18)
            self.assertEqual(pix.height() / pix.devicePixelRatio(), 18)

            ico = icons.get_icon(name, "#ffffff", 16)
            self.assertFalse(ico.isNull())

        # Test caching
        ico1 = icons.get_icon("dashboard", "#3b82f6", 16)
        ico2 = icons.get_icon("dashboard", "#3b82f6", 16)
        self.assertIs(ico1, ico2)

    def test_no_emojis_in_gui_modules(self):
        from pathlib import Path
        gui_dir = ROOT / "tools" / "gui"
        for py_file in gui_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            for line_no, line in enumerate(content.splitlines(), 1):
                non_ascii = [c for c in line if ord(c) > 127 and c not in "äöüÄÖÜß·–—•éè"]
                self.assertEqual(
                    non_ascii, [],
                    f"Forbidden non-ascii/emoji character found in {py_file.name}:{line_no}: {''.join(non_ascii)}"
                )


if __name__ == "__main__":
    unittest.main()

