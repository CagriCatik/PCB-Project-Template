"""Installer payload, registry, CLI and fail-closed quality-gate tests."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.plugins import install_archive, install_ibom
from tools.template_engine import create, install
from tools.kicad_cli import KiCadCLI, verify
from tools.common import git_state
from tools.registry import register_project


class ToolTests(unittest.TestCase):
    def test_command_installer_and_spaces(self):
        with tempfile.TemporaryDirectory(prefix="command spaces ") as d:
            for _ in range(2):
                subprocess.run(
                    [str(ROOT / "install_template.command"), "--parent", d],
                    check=True,
                    capture_output=True,
                )
            self.assertTrue((Path(d) / "embedded-hw-fw/meta/info.html").exists())
            for cmd in [
                "create-project",
                "open-project",
                "verify",
                "install-plugins",
                "export-manufacturing",
                "diagnose",
            ]:
                subprocess.run(
                    [str(ROOT / "scripts" / (cmd + ".sh")), "--help"],
                    check=True,
                    capture_output=True,
                )

    def test_plugin_zip_install_repeat_and_traversal(self):
        with tempfile.TemporaryDirectory(prefix="plugin space ") as d:
            root = Path(d)
            archive = root / "plugin.zip"
            user = root / "global"
            metadata = {
                "identifier": "app.freerouting.kicad-plugin",
                "type": "plugin",
                "versions": [{"version": "test", "kicad_version": "10.0"}],
            }
            with zipfile.ZipFile(archive, "w") as z:
                z.writestr("metadata.json", json.dumps(metadata))
                z.writestr("plugins/__init__.py", "# test fixture only")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(
                install_archive("freerouting", archive, digest, user)["status"],
                "INSTALLED",
            )
            self.assertEqual(
                install_archive("freerouting", archive, digest, user)["status"],
                "ALREADY_INSTALLED",
            )
            with self.assertRaises(ValueError):
                install_archive("freerouting", archive, "0" * 64, user)
            with zipfile.ZipFile(archive, "a") as z:
                z.writestr("../escape", "bad")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):
                install_archive("freerouting", archive, digest, user)
            self.assertFalse((root / "escape").exists())

    def test_registry_is_global_and_idempotent(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(
            os.environ, {"KICAD_KIT_HOME": d}
        ):
            register_project(ROOT)
            data = register_project(ROOT)
            self.assertEqual(len(data["projects"]), 1)
            self.assertTrue((Path(d) / "projects.json").exists())

    def test_git_init_never_commits(self):
        with tempfile.TemporaryDirectory() as d:
            p = create(ROOT, Path(d) / "Board", "Board", "generic", True, False)
            self.assertTrue((p / ".git").is_dir())
            self.assertIsNone(git_state(p)["commit"])

    def test_optional_firmware_is_not_a_fake_build(self):
        with tempfile.TemporaryDirectory() as d:
            for workflow in ["stm32", "arduino"]:
                p = create(ROOT, Path(d) / workflow, workflow, workflow, False, False)
                self.assertEqual(
                    json.loads((p / "firmware/config/workflow.json").read_text())[
                        "status"
                    ],
                    "TARGET_CONFIGURATION_REQUIRED",
                )
                from tools.firmware import build

                with self.assertRaises(ValueError):
                    build(p, workflow)

    def test_cli_version_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "fake cli"
            fake.write_text("#!/bin/sh\necho 9.0.0\n")
            fake.chmod(0o755)
            with self.assertRaises(ValueError):
                KiCadCLI(fake)

    def test_live_project_locks_block_automation(self):
        with tempfile.TemporaryDirectory() as d:
            p = create(ROOT, Path(d) / "Board", "Board", "generic", False, False)
            (p / "~Board.kicad_pro.lck").write_text("test")
            with self.assertRaises(ValueError):
                verify(p)

    def test_source_update_leaves_installed_template_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "source"
            src.mkdir()
            (src / "meta").mkdir()
            (src / "meta/info.html").write_text("<title>T</title>")
            (src / "notes").write_text("first")
            target = install(src, root / "installed")
            (src / "notes").write_text("second")
            with self.assertRaises(ValueError):
                install(src, root / "installed")
            self.assertEqual((target / "notes").read_text(), "first")


class GateTests(unittest.TestCase):
    def test_report_warnings_and_exclusions_block_even_zero_exit(self):
        class FakeCLI:
            version = "10.0.7"
            version_record = {"exit_code": 0, "stdout": "10.0.7"}

            def call(self, *args):
                output = Path(args[args.index("-o") + 1])
                report = (
                    {"sheets": [{"violations": [{"severity": "exclusion"}]}]}
                    if args[0] == "sch"
                    else {
                        "violations": [],
                        "unconnected_items": [],
                        "schematic_parity": [],
                    }
                )
                output.write_text(json.dumps(report))
                return {
                    "argv": [str(x) for x in args],
                    "exit_code": 0,
                    "stdout": "",
                    "stderr": "",
                }

        with tempfile.TemporaryDirectory() as d:
            p = create(ROOT, Path(d) / "Board", "Board", "generic", False, False)
            result = verify(p, FakeCLI())
            self.assertEqual(result["quality_gate"], "FAIL")
            self.assertEqual(result["finding_count"], 1)

    def test_release_approval_bound_to_revision_and_commit(self):
        from tools.release import GATES, check_approval

        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "approval.json"
            data = {
                "decision": "GO",
                "revision": "A",
                "commit": "abc",
                "approver": "Test reviewer (fixture)",
                "date": "2026-10-18",
                "signed_checklist": "checklist.txt",
                "gates": {
                    g: {"status": "PASS", "evidence": "fixture.txt"} for g in GATES
                },
            }
            p.write_text(json.dumps(data))
            self.assertEqual(check_approval(p, "A", "abc")["decision"], "GO")
            with self.assertRaises(ValueError):
                check_approval(p, "B", "abc")
            with self.assertRaises(ValueError):
                check_approval(p, "A", "def")
            data["gates"]["prototype_validation"]["status"] = "OPEN"
            p.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                check_approval(p, "A", "abc")

    def test_ibom_checkout_repeat_preserves_modifications(self):
        with tempfile.TemporaryDirectory(prefix="ibom spaces ") as d:
            root = Path(d)
            repo = root / "repo"
            repo.mkdir()
            (repo / "InteractiveHtmlBom").mkdir()
            (repo / "InteractiveHtmlBom/__init__.py").write_text("# fixture")
            commands = [
                ["init"],
                ["add", "."],
                [
                    "-c",
                    "user.name=Fixture",
                    "-c",
                    "user.email=fixture@example.invalid",
                    "commit",
                    "-m",
                    "fixture",
                ],
                ["tag", "v2.12.0"],
                [
                    "remote",
                    "add",
                    "origin",
                    "https://github.com/openscopeproject/InteractiveHtmlBom.git",
                ],
            ]
            for cmd in commands:
                subprocess.run(
                    ["git", "-C", str(repo), *cmd], check=True, capture_output=True
                )
            for _ in range(2):
                self.assertEqual(
                    install_ibom(root / "plugins", repo)["status"], "INSTALLED"
                )
            (repo / "InteractiveHtmlBom/__init__.py").write_text("# user edit")
            with self.assertRaises(ValueError):
                install_ibom(root / "plugins", repo)
            self.assertEqual(
                (repo / "InteractiveHtmlBom/__init__.py").read_text(), "# user edit"
            )


class PluginDiagnosticsTests(unittest.TestCase):
    def test_pcm_config_database_precedes_legacy_data_directory(self):
        from tools.plugins import diagnose

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "user data"
            config = Path(directory) / "config"
            (root / "3rdparty/plugins/org_openscopeproject_InteractiveHtmlBom").mkdir(
                parents=True
            )
            config.mkdir()

            def database(version):
                return {
                    "packages": [
                        {
                            "package": {
                                "identifier": "org.openscopeproject.InteractiveHtmlBom"
                            },
                            "current_version": version,
                        }
                    ]
                }

            (config / "installed_packages.json").write_text(
                json.dumps(database("2.12.0"))
            )
            (root / "3rdparty/installed_packages.json").write_text(
                json.dumps(database("old"))
            )
            with patch("tools.plugins.run", return_value={"exit_code": 0}):
                result = diagnose(root, config)
            self.assertEqual(result["plugins"][0]["pcm_version"], "2.12.0")
            self.assertEqual(
                result["package_database"], str(config / "installed_packages.json")
            )
            self.assertTrue(result["plugins"][0]["pcm_present"])

    def test_pcm_legacy_database_fallback(self):
        from tools.plugins import diagnose

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data"
            (root / "3rdparty").mkdir(parents=True)
            database = root / "3rdparty/installed_packages.json"
            database.write_text(json.dumps({"packages": []}))
            with patch("tools.plugins.run", return_value={"exit_code": 0}):
                result = diagnose(root, Path(directory) / "absent config")
            self.assertEqual(result["package_database"], str(database))


if __name__ == "__main__":
    unittest.main()
