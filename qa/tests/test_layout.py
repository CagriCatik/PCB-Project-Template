"""Repository layout, ownership boundaries, preservation and documentation accuracy."""

import hashlib
import json
import os
import re
import unittest

from kit_test_support import ROOT

MANDATORY = ["AGENTS.md", "LICENSE", "README.md", "requirements.txt", "install_template.command",
             "test_template.py", "hardware", "firmware", "components", "manufacturing", "docs", "qa",
             "scripts", "tools", "meta"]
REQUIRED_DOCS = ["ARCHITECTURE", "INSTALLATION", "PROJECT_STRUCTURE", "PLUGIN_MANAGEMENT", "KICAD_IPC",
                 "CLI_REFERENCE", "MANUFACTURING", "VERIFICATION", "TROUBLESHOOTING", "LESSONS_LEARNED",
                 "IMPLEMENTATION_STATUS", "ACCEPTANCE_REPORT", "THERMAL_ANALYSIS",
                 "KICAD_COMPATIBILITY", "LIBRARY_MANAGEMENT"]
# Original files deliberately relocated (bytes preserved) to resolve case-insensitive
# collisions with required docs or to separate kit and project content.
RELOCATED = {
    "docs/architecture.md": "docs/project-template/architecture.md",
    "docs/bringup.md": "docs/project-template/bringup.md",
    "docs/interfaces.md": "docs/project-template/interfaces.md",
    "docs/requirements.md": "docs/project-template/requirements.md",
    "docs/verification-plan.md": "docs/project-template/verification-plan.md",
    "docs/decisions/ADR-0001-repo-boundaries.md": "docs/project-template/decisions/ADR-0001-repo-boundaries.md",
    "qa/tests/README.md": "qa/project-template/tests/README.md",
}
# Originals intentionally edited (entrypoints, onboarding, rules), user-edited (LICENSE),
# or fixed by the previous iteration (install-kicad.sh path quoting).
EDITED = {"README.md", "LICENSE", "AGENTS.md", "install_template.command", "test_template.py",
          "requirements.txt", ".gitignore", "scripts/install-plugins.sh", "tools/verify.sh",
          "scripts/install-kicad.sh"}
# Removed earlier with explicit user authorization (content merged into README.md).
RETIRED = {"README Kopie.md"}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LayoutTests(unittest.TestCase):
    def test_mandatory_top_level_entries(self):
        for name in MANDATORY:
            self.assertTrue((ROOT / name).exists(), name)

    def test_entrypoints_are_executable(self):
        for name in ["install_template.command", "project-manager.command", "gui.command", "scripts/kit"] + [
                "scripts/" + p.name for p in (ROOT / "scripts").glob("*.sh")]:
            path = ROOT / name
            self.assertTrue(path.is_file() and os.access(path, os.X_OK), name)
            self.assertTrue(path.read_text().startswith("#!/bin/bash"), name)

    def test_kit_root_is_not_itself_a_board(self):
        # Templates materialize native files; the kit root holds none, so KiCad
        # never sees two competing projects.
        self.assertEqual(list(ROOT.glob("*.kicad_pro")), [])

    def test_ownership_boundaries(self):
        self.assertTrue((ROOT / "hardware/native-defaults/default.kicad_pcb").is_file())
        self.assertTrue((ROOT / "firmware/templates/common/app/src/heartbeat.c").is_file())
        for template in ("generic-pcb", "stm32-embedded", "arduino-shield"):
            self.assertTrue((ROOT / "meta/templates" / template / "meta/info.html").is_file())
        # Business logic lives in tools/; scripts are thin wrappers around scripts/kit.
        for script in (ROOT / "scripts").glob("*.sh"):
            text = script.read_text()
            if script.name not in ("install-kicad.sh", "install-vscode-extensions.sh"):  # standalone installers
                self.assertIn("/kit", text, script.name)
                self.assertLess(len(text.splitlines()), 10, script.name)
        # Application code never includes target headers.
        app = (ROOT / "firmware/templates/common/app/src/heartbeat.c").read_text()
        self.assertNotRegex(app, r'#include\s*[<"](Arduino|stm32|main)\b')

    def test_tools_package_layering(self):
        """Imports inside tools/ only point to allowed (lower) packages; all are absolute."""
        allowed = {
            "core": set(),
            "kicad": {"core"},
            "plugins": {"core"},
            "thermal": {"core"},
            "project": {"core", "kicad"},
            "quality": {"core", "kicad", "project", "thermal"},
            "release": {"core", "kicad", "quality", "plugins"},
            "environment": {"core", "kicad", "project", "quality", "plugins"},
            "gui": {"core", "kicad", "project", "quality", "release", "plugins", "environment", "thermal"},
            "cli": {"core", "kicad", "project", "quality", "release", "plugins", "environment", "thermal", "gui"},
        }
        for path in sorted((ROOT / "tools").rglob("*.py")):
            rel = path.relative_to(ROOT / "tools").parts
            package = rel[0] if len(rel) > 1 else None
            text = path.read_text()
            self.assertNotRegex(text, r"(?m)^\s*from \.", "%s uses a relative import" % path.name)
            for target in re.findall(r"(?m)^\s*(?:from|import) tools\.(\w+)", text):
                if package is None:
                    continue  # tools/__init__.py, tools/__main__.py
                if target != package:
                    self.assertIn(target, allowed[package], "%s imports tools.%s" % ("/".join(rel), target))
        self.assertEqual({p.name for p in (ROOT / "tools").iterdir() if p.is_dir() and p.name != "__pycache__"},
                         set(allowed))

    def test_required_docs_exist_and_are_substantive(self):
        for doc in REQUIRED_DOCS:
            path = ROOT / "docs" / (doc + ".md")
            self.assertTrue(path.is_file(), doc)
            text = path.read_text()
            self.assertGreater(len(text), 600, doc)
            self.assertNotIn("TODO", text, doc)

    def test_no_case_insensitive_collisions(self):
        for folder in [ROOT] + [p for p in ROOT.rglob("*") if p.is_dir() and ".git" not in p.parts]:
            names = [p.name.lower() for p in folder.iterdir()]
            self.assertEqual(len(names), len(set(names)), folder)

    def test_original_files_preserved(self):
        inventory = json.loads((ROOT / "docs/archive/2026-10-18-previous-iteration/baseline-inventory.json")
                               .read_text())["entries"]
        for entry in inventory:
            path, digest = entry["path"], entry.get("sha256")
            if path in RETIRED or path.endswith(".DS_Store") or not digest:
                continue
            with self.subTest(path=path):
                if path in RELOCATED:
                    self.assertEqual(sha(ROOT / RELOCATED[path]), digest)
                elif path in EDITED:
                    self.assertTrue((ROOT / path).is_file())
                else:
                    self.assertEqual(sha(ROOT / path), digest)

    def test_csv_contracts_have_unique_columns(self):
        import csv

        for rel in ("hardware/interfaces/pinmap.csv", "hardware/interfaces/power_budget.csv",
                    "components/bom_master.csv", "components/sources.csv"):
            with (ROOT / rel).open(newline="") as fp:
                header = next(csv.reader(fp))
            self.assertEqual(len(header), len(set(header)), rel)

    def test_docs_reference_only_real_cli_commands(self):
        from tools.cli.main import build_parser

        parser = build_parser()
        commands = set(parser._subparsers._group_actions[0].choices)
        docs = [ROOT / "README.md", ROOT / "AGENTS.md"] + sorted((ROOT / "docs").glob("*.md"))
        for doc in docs:
            for cmd in re.findall(r"scripts/kit ([a-z][a-z-]+)", doc.read_text()):
                self.assertIn(cmd, commands, "%s mentions unknown 'scripts/kit %s'" % (doc.name, cmd))

    def test_gitignore_excludes_local_and_generated_state(self):
        text = (ROOT / ".gitignore").read_text()
        for pattern in ("*.kicad_prl", "*-backups/", ".venv/", "qa/generated/", "manufacturing/releases/generated/",
                        "~*.lck"):
            self.assertIn(pattern, text)


if __name__ == "__main__":
    unittest.main()
