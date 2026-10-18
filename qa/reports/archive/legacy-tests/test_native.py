"""Real KiCad integration; opt in with KICAD_NATIVE_TESTS=1. No mock pass claims."""

import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.template_engine import create
from tools.kicad_cli import KiCadCLI, verify
from tools.release import export_project


@unittest.skipUnless(
    os.environ.get("KICAD_NATIVE_TESTS") == "1",
    "set KICAD_NATIVE_TESTS=1 for actual KiCad integration",
)
class NativeTests(unittest.TestCase):
    def test_native_project_verification_and_exports(self):
        cli = KiCadCLI()
        bundled = os.environ.get(
            "KICAD_PCBNEW_PYTHON",
            "/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/3.9/bin/python3",
        )
        with tempfile.TemporaryDirectory(prefix="KiCad native test ") as d:
            root = create(
                ROOT, Path(d) / "Native Board", "Native Board", "generic", False, False
            )
            blank = verify(root, cli)
            self.assertEqual(blank["quality_gate"], "FAIL")
            self.assertTrue(blank["source_unchanged"])
            self.assertIn(
                "invalid_outline",
                (Path(blank["report_directory"]) / "drc.json").read_text(),
            )
            # Genuine pcbnew API creates a mechanical-only rectangular fixture.
            script = """import pcbnew,sys
assert pcbnew.Version() == '10.0.7'
board=pcbnew.LoadBoard(sys.argv[1])
shape=pcbnew.PCB_SHAPE(board)
shape.SetShape(pcbnew.SHAPE_T_RECT)
shape.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(100),pcbnew.FromMM(100)))
shape.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(150),pcbnew.FromMM(150)))
shape.SetLayer(pcbnew.Edge_Cuts)
shape.SetWidth(pcbnew.FromMM(0.05))
board.Add(shape)
assert pcbnew.SaveBoard(sys.argv[1],board)
"""
            subprocess.run(
                [bundled, "-c", script, str(root / "Native Board.kicad_pcb")],
                check=True,
                capture_output=True,
            )
            good = verify(root, cli)
            self.assertEqual(good["quality_gate"], "PASS", good)
            self.assertTrue(good["source_unchanged"])
            target, manifest = export_project(root, "test-A", cli=cli)
            self.assertTrue(manifest["exports_complete"], manifest["commands"])
            self.assertEqual(manifest["decision"], "NO-GO")
            self.assertEqual(manifest["quality_gate"], "PASS")
            self.assertTrue((target / "board.step").stat().st_size > 0)
            archive = ROOT / "qa/generated/native-integration"
            archive.mkdir(parents=True, exist_ok=True)
            evidence = Path(tempfile.mkdtemp(prefix="run-", dir=archive))
            shutil.copytree(target, evidence / "draft-exports")
            shutil.copytree(
                blank["report_directory"], evidence / "expected-blank-failure"
            )
            shutil.copytree(
                good["report_directory"], evidence / "expected-outline-pass"
            )
            print("Native evidence: " + str(evidence))
            with self.assertRaises(ValueError):
                export_project(root, "test-A", cli=cli)
            # Native source is deliberately corrupted to test real CLI failure.
            (root / "Native Board.kicad_sch").write_text("(invalid")
            self.assertEqual(verify(root, cli)["quality_gate"], "FAIL")


if __name__ == "__main__":
    unittest.main()
