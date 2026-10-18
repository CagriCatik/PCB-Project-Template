"""Preservation and behavior contracts, independent of the native CLI suite."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools import template_engine
from tools.libraries import register_library
from tools.release import check_approval

MANDATORY = [
    "AGENTS.md",
    "LICENSE",
    "README.md",
    "requirements.txt",
    "install_template.command",
    "test_template.py",
    "hardware",
    "firmware",
    "components",
    "manufacturing",
    "docs",
    "qa",
    "scripts",
    "tools",
    "meta",
]


# Explicitly authorized after review: unique onboarding was merged into README.md.
RETIRED_FILES = {"README Kopie.md"}

# Existing workspace update observed during cleanup: completed copyright name.
# Keep the historical baseline intact and accept only these exact reviewed bytes.
REVIEWED_HASH_UPDATES = {
    "LICENSE": "3a8d004ed4f446eb2ad1f9b3d7e05f336d21fcbd2937092ea7a9a061ee0dc60a",
}


class PreservationTests(unittest.TestCase):
    def test_original_entries_accessible(self):
        if list(ROOT.glob("*.kicad_pro")):
            self.skipTest(
                "Repository-preservation audit applies to the source kit, not adapted board designs"
            )
        for entry in json.loads((ROOT / "docs/baseline-inventory.json").read_text())[
            "entries"
        ]:
            if entry["path"] in RETIRED_FILES:
                continue
            if Path(entry["path"]).name in (".DS_Store", "Thumbs.db"):
                continue
            self.assertTrue((ROOT / entry["path"]).exists(), entry["path"])
        for name in MANDATORY:
            self.assertTrue((ROOT / name).exists(), name)

    def test_unmodified_baseline_files(self):
        if list(ROOT.glob("*.kicad_pro")):
            self.skipTest("Generated board documentation is intentionally editable")
        allowed = {
            "README.md",
            "docs/conventions.md",
            "requirements.txt",
            "install_template.command",
            "test_template.py",
            "tools/verify.sh",
            ".gitignore",
            "scripts/install-plugins.sh",
            "scripts/install-kicad.sh",
        }
        for entry in json.loads((ROOT / "docs/baseline-inventory.json").read_text())[
            "entries"
        ]:
            if entry["path"] in RETIRED_FILES:
                continue
            if Path(entry["path"]).name in (".DS_Store", "Thumbs.db"):
                continue
            if "sha256" in entry and entry["path"] not in allowed:
                self.assertEqual(
                    hashlib.sha256((ROOT / entry["path"]).read_bytes()).hexdigest(),
                    REVIEWED_HASH_UPDATES.get(entry["path"], entry["sha256"]),
                    entry["path"],
                )

    def test_install_repeat_preserves_user_files(self):
        with tempfile.TemporaryDirectory(prefix="template space ") as d:
            target = template_engine.install(ROOT, Path(d))
            (target / "my notes.txt").write_text("keep")
            template_engine.install(ROOT, Path(d))
            self.assertEqual((target / "my notes.txt").read_text(), "keep")
            self.assertEqual(len(list(Path(d).glob("embedded-hw-fw"))), 1)
            self.assertFalse((target / ".git").exists())
            self.assertTrue((target / ".gitignore").is_file())

    def test_install_conflict_does_not_replace(self):
        with tempfile.TemporaryDirectory() as d:
            t = Path(d) / "embedded-hw-fw"
            t.mkdir()
            (t / "unrelated").write_text("keep")
            with self.assertRaises(ValueError):
                template_engine.install(ROOT, Path(d))
            self.assertEqual((t / "unrelated").read_text(), "keep")

    def test_project_generation_portability_and_collision(self):
        with tempfile.TemporaryDirectory(prefix="project space ") as d:
            p = template_engine.create(
                ROOT, Path(d) / "My Board", "My Board", "generic", False, False
            )
            for name in MANDATORY:
                self.assertTrue((p / name).exists(), name)
            for ext in ("kicad_pro", "kicad_pcb", "kicad_sch"):
                self.assertTrue((p / ("My Board." + ext)).is_file())
            self.assertFalse((p / ".venv").exists())
            self.assertFalse((p / "3rdparty").exists())
            self.assertFalse((p / "qa/generated").exists())
            with self.assertRaises(ValueError):
                template_engine.create(ROOT, p, "My Board", "generic", False, False)
            subprocess.run(
                [sys.executable, str(p / "test_template.py")],
                check=True,
                capture_output=True,
            )

    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                template_engine.create(
                    ROOT, Path(d) / "out", "../escape", "generic", False, False
                )

    def test_symlinks_are_not_copied(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "meta").mkdir()
            (p / "meta/info.html").write_text("<title>test</title>")
            (p / "secret").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                template_engine.source_files(p)

    def test_library_registration_idempotent(self):
        with tempfile.TemporaryDirectory(prefix="lib space ") as d:
            p = Path(d)
            (p / "hardware/libraries/symbols").mkdir(parents=True)
            lib = p / "hardware/libraries/symbols/Test.kicad_sym"
            lib.write_text(
                '(kicad_symbol_lib (version 20241209) (generator "kicad_symbol_editor"))'
            )
            register_library(p, "symbol", "Test", lib)
            original = (p / "sym-lib-table").read_text()
            register_library(p, "symbol", "Test", lib)
            self.assertEqual(original, (p / "sym-lib-table").read_text())
            self.assertIn("${KIPRJMOD}", original)

    def test_unsigned_release_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "approval.json"
            p.write_text("{}")
            with self.assertRaises(ValueError):
                check_approval(p, "A", "deadbeef")

    def test_shell_entrypoints_syntax(self):
        for p in list((ROOT / "scripts").glob("*.sh")) + [
            ROOT / "install_template.command",
            ROOT / "tools/verify.sh",
        ]:
            subprocess.run(["bash", "-n", str(p)], check=True)


if __name__ == "__main__":
    unittest.main()
