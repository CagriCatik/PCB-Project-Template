"""One-time installation, repeated installation and preservation of foreign state."""

import json
import subprocess

from kit_test_support import NATIVE, ROOT, EnvPatch, TempDirTest, requires_kicad
from tools.environment import installer as environment


@requires_kicad
class InstallerTests(TempDirTest):
    def run_install(self, templates):
        return environment.install(skip_venv=True, template_dir=templates, verify_plugins=False,
                                   report_path=self.tmp / "report.json")

    def test_first_and_repeated_installation(self):
        templates = self.tmp / "KiCad user templates"
        first = self.run_install(templates)
        steps = {s["step"]: s for s in first["steps"]}
        self.assertNotEqual(first["overall"], "FAIL", first["failed"])
        self.assertEqual(steps["kicad"]["status"], "PASS")
        self.assertEqual(steps["kicad_templates"]["status"], "CHANGED")
        self.assertEqual(steps["library_paths"]["status"], "PASS")
        self.assertEqual({r["action"] for r in steps["kicad_templates"]["results"]}, {"INSTALLED"})
        snapshot = {p.relative_to(templates).as_posix(): p.read_bytes() for p in templates.rglob("*") if p.is_file()}
        second = self.run_install(templates)
        steps = {s["step"]: s for s in second["steps"]}
        self.assertEqual(steps["kicad_templates"]["status"], "UNCHANGED")
        self.assertEqual(second["changed"], [])
        after = {p.relative_to(templates).as_posix(): p.read_bytes() for p in templates.rglob("*") if p.is_file()}
        self.assertEqual(snapshot, after, "a repeated installation must not rewrite anything")
        report = json.loads((self.tmp / "report.json").read_text())
        self.assertEqual(report["kind"], "install")
        self.assertIn("ipc", {s["step"] for s in report["steps"]})

    def test_foreign_template_directory_is_preserved(self):
        templates = self.tmp / "templates"
        (templates / "arduino-shield").mkdir(parents=True)
        (templates / "arduino-shield/keep.txt").write_text("user file")
        report = self.run_install(templates)
        step = next(s for s in report["steps"] if s["step"] == "kicad_templates")
        self.assertEqual(step["status"], "WARN")
        actions = {r["template"]: r["action"] for r in step["results"]}
        self.assertEqual(actions["arduino-shield"], "SKIPPED_FOREIGN")
        self.assertEqual((templates / "arduino-shield/keep.txt").read_text(), "user file")

    def test_missing_kicad_aborts_before_writing(self):
        templates = self.tmp / "templates"
        with EnvPatch(KICAD_CLI=str(self.tmp / "missing-cli")):
            report = self.run_install(templates)
        self.assertEqual(report["overall"], "FAIL")
        self.assertIn("abort", report["failed"])
        self.assertFalse(templates.exists())

    def test_doctor_is_read_only(self):
        templates = self.tmp / "templates"
        with EnvPatch(KICAD_USER_TEMPLATE_DIR=str(templates)):
            report = environment.doctor(report_path=self.tmp / "doctor.json")
        self.assertFalse(templates.exists())
        self.assertEqual(report["changed"], [])
        state = next(s for s in report["steps"] if s["step"] == "kicad_templates")
        self.assertEqual({t["state"] for t in state["templates"]}, {"NOT_INSTALLED"})


class InstallerEntrypointTests(TempDirTest):
    def test_command_file_passes_options_and_exit_status(self):
        env = {"KICAD_CLI": str(self.tmp / "missing"), "PATH": "/usr/bin:/bin:/opt/homebrew/bin:/usr/local/bin"}
        with EnvPatch(**env):
            result = subprocess.run([str(ROOT / "install_template.command"), "--skip-venv", "--no-plugin-verify",
                                     "--template-dir", str(self.tmp / "t"), "--report", str(self.tmp / "r.json")],
                                    capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("kicad-cli not found", result.stdout)
        self.assertTrue((self.tmp / "r.json").is_file())

    def test_venv_stamp_skips_reinstall(self):
        # Never install from a test: only exercise setup_venv when it must be a no-op.
        if not environment.venv_up_to_date():
            self.skipTest("repository .venv missing or older than requirements.txt; run ./install_template.command")
        step = environment.setup_venv()
        self.assertEqual(step["status"], "UNCHANGED", step)


if __name__ == "__main__":
    import unittest

    unittest.main()
