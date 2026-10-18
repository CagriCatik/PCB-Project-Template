#!/usr/bin/env python3
"""Run the complete kit test suite (structure, tooling and native KiCad integration).

Usage: python3 test_template.py [-v] [-k PATTERN]
Native KiCad 10.0.7 tests run automatically when KiCad is installed;
set KICAD_NATIVE_TESTS=0 to skip them. Runs under the kit's .venv when it exists
(set KIT_TESTS_NO_VENV=1 to use the current interpreter). See qa/tests/README.md.
"""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent
TESTS = ROOT / "qa" / "tests"


class TemplateTests(unittest.TestCase):
    """Fast structural checks that also document the template contract."""

    def test_template_metadata_has_titles(self):
        from html.parser import HTMLParser

        for info in [ROOT / "meta/info.html"] + sorted((ROOT / "meta/templates").glob("*/meta/info.html")):
            text = info.read_text()
            self.assertRegex(text.lower(), r"<title>[^<]+</title>", str(info))

    def test_three_templates_declared(self):
        import json

        ids = {json.loads(p.read_text())["id"] for p in (ROOT / "meta/templates").glob("*/template.json")}
        self.assertEqual(ids, {"generic-pcb", "stm32-embedded", "arduino-shield"})

    def test_pinmap_columns_unique(self):
        import csv

        with (ROOT / "hardware/interfaces/pinmap.csv").open(newline="") as fp:
            header = next(csv.reader(fp))
        self.assertEqual(len(header), len(set(header)))
        self.assertIn("schematic_net", header)
        self.assertIn("firmware_signal", header)

    def test_policy_files_present(self):
        for name in ("AGENTS.md", ".gitignore", ".gitattributes", "requirements.txt"):
            self.assertTrue((ROOT / name).is_file(), name)


def suite(pattern="test*.py"):
    sys.path.insert(0, str(TESTS))
    loader = unittest.TestLoader()
    all_tests = unittest.TestSuite([loader.loadTestsFromTestCase(TemplateTests)])
    all_tests.addTests(loader.discover(str(TESTS), pattern=pattern, top_level_dir=str(TESTS)))
    return all_tests


def _reexec_in_venv():
    """Prefer the kit's .venv (it has numpy/scipy for the thermal tests)."""
    import os

    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.is_file() and Path(sys.prefix).resolve() != (ROOT / ".venv").resolve() \
            and not os.environ.get("KIT_TESTS_NO_VENV"):
        os.execv(str(venv_python), [str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:])


if __name__ == "__main__":
    import argparse

    _reexec_in_venv()

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("-k", "--pattern", default="test*.py", help="test module glob, e.g. 'test_ipc.py'")
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2 if args.verbose else 1).run(suite(args.pattern))
    sys.exit(0 if result.wasSuccessful() else 1)
