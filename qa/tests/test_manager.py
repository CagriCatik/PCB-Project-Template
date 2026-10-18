"""Interactive manager driven by scripted input, plus the non-interactive CLI."""

import io
import json
import os
import subprocess
from contextlib import redirect_stdout

from kit_test_support import ROOT, TempDirTest, requires_kicad
from tools.cli.main import main
from tools.cli.interactive import Manager


class Scripted:
    def __init__(self, answers):
        self.answers, self.output = list(answers), []

    def ask(self, prompt):
        self.output.append(prompt)
        if not self.answers:
            raise EOFError
        return self.answers.pop(0)

    def say(self, text):
        self.output.append(str(text))

    @property
    def text(self):
        return "\n".join(self.output)


class ManagerTests(TempDirTest):
    def test_create_project_with_retry_on_invalid_name(self):
        # Menu answers: create, template 2 (generic-pcb), profile 1 (2-layer), bad name, good name,
        # parent, no git, confirm, list projects, exit.
        parent = self.tmp / "my projects"
        io_ = Scripted(["1", "2", "1", "bad/name", "Board With Spaces", str(parent), "n", "y", "9", "0"])
        self.assertEqual(Manager(io_.ask, io_.say).run(), 0)
        project = parent / "Board With Spaces"
        self.assertTrue((project / "Board With Spaces.kicad_pro").is_file())
        self.assertIn("Project name must", io_.text)
        self.assertIn("Created and selected", io_.text)
        self.assertIn(str(project), io_.text)  # listed by option 9
        self.assertFalse((project / ".git").exists())
        self.assertEqual(__import__("json").loads((project / "meta/project.json").read_text())["profile"], "2-layer")

    def test_cancel_creates_nothing(self):
        parent = self.tmp / "p"
        io_ = Scripted(["1", "2", "2", "Cancelled Board", str(parent), "n", "n", "0"])
        Manager(io_.ask, io_.say).run()
        self.assertFalse((parent / "Cancelled Board").exists())
        self.assertIn("Cancelled.", io_.text)

    def test_existing_destination_is_reported_not_overwritten(self):
        parent = self.tmp / "p"
        (parent / "Taken").mkdir(parents=True)
        (parent / "Taken/file.txt").write_text("mine")
        io_ = Scripted(["1", "2", "1", "Taken", str(parent), "n", "y", "0"])
        Manager(io_.ask, io_.say).run()
        self.assertIn("ERROR: Destination exists", io_.text)
        self.assertEqual(os.listdir(parent / "Taken"), ["file.txt"])

    def test_open_non_project_path_and_unknown_choice(self):
        io_ = Scripted(["2", str(self.tmp), "42", "0"])
        Manager(io_.ask, io_.say).run()
        self.assertIn("ERROR: Expected exactly one root .kicad_pro", io_.text)
        self.assertIn("Unknown choice '42'", io_.text)

    def test_end_of_input_exits_cleanly(self):
        io_ = Scripted([])
        self.assertEqual(Manager(io_.ask, io_.say).run(), 0)

    @requires_kicad
    def test_select_fixture_and_run_checks(self):
        board = self.fixture_copy()
        io_ = Scripted(["2", str(board), "5", "0"])
        Manager(io_.ask, io_.say).run()
        self.assertIn("Quality gate: PASS", io_.text)

    def test_command_launcher_runs_menu(self):
        result = subprocess.run([str(ROOT / "project-manager.command")], input="0\n", capture_output=True,
                                text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PCB Project Manager", result.stdout)
        self.assertIn("0) Exit", result.stdout)


class CliTests(TempDirTest):
    def call(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = main(list(argv))
        return code, out.getvalue()

    def test_create_via_cli_with_spaces_and_json(self):
        code, out = self.call("create", "--template", "stm32-embedded", "--name", "CLI Board", "--dest",
                              str(self.tmp / "a b" / "CLI Board"), "--no-register", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["record"]["template"], "stm32-embedded")
        code, _ = self.call("create", "--template", "stm32-embedded", "--name", "CLI Board", "--dest",
                            str(self.tmp / "a b" / "CLI Board"), "--no-register")
        self.assertEqual(code, 18)

    def test_legacy_firmware_flag_maps_to_template(self):
        code, out = self.call("create", "--firmware", "generic", "--name", "Legacy", "--dest",
                              str(self.tmp / "Legacy"), "--no-register", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["record"]["template"], "generic-pcb")

    def test_invalid_name_exit_code(self):
        code, _ = self.call("create", "--template", "generic-pcb", "--name", "x/y", "--dest", str(self.tmp / "z"))
        self.assertEqual(code, 2)

    def test_plugin_guide_and_templates_list(self):
        self.assertEqual(self.call("plugins", "guide", "board2pdf")[0], 0)
        code, out = self.call("templates", "list", "--json")
        self.assertEqual({r["id"] for r in json.loads(out)}, {"generic-pcb", "stm32-embedded", "arduino-shield"})

    @requires_kicad
    def test_verify_exit_codes(self):
        board = self.fixture_copy()
        self.assertEqual(self.call("verify", str(board))[0], 0)
        self.assertEqual(self.call("verify", str(board), "--release")[0], 20)
