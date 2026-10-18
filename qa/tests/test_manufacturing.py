"""Manufacturing exports, reproducibility and the fail-closed release gate."""

import json
from pathlib import Path
import re
import shutil
from unittest import mock

from kit_test_support import EnvPatch, TempDirTest, requires_kicad
from tools.release import exports as release
from tools.core.common import KitError

CLEAN = {"commit": "a" * 40, "dirty": False, "status": ""}


def approval_file(board, revision="R1", commit="a" * 40):
    evidence = board / "qa/design-reviews/evidence.md"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("Signed review evidence (test-only).\n")
    (board / "manufacturing/releases").mkdir(parents=True, exist_ok=True)
    (board / "manufacturing/releases/RELEASE_CHECKLIST.md").write_text("Signed checklist (test-only).\n")
    data = {"decision": "GO", "revision": revision, "commit": commit, "approver": "unit test",
            "date": "2026-10-18", "signed_checklist": "manufacturing/releases/RELEASE_CHECKLIST.md",
            "gates": {g: {"status": "PASS", "evidence": "qa/design-reviews/evidence.md"} for g in release.GATES}}
    path = board.parent / ("approval-%s.json" % revision)
    path.write_text(json.dumps(data))
    return path


class ApprovalTests(TempDirTest):
    def test_approval_must_bind_revision_commit_and_every_gate(self):
        board = self.fixture_copy()
        path = approval_file(board)
        self.assertEqual(release.check_approval(path, "R1", "a" * 40)["decision"], "GO")
        for revision, commit in (("R2", "a" * 40), ("R1", "b" * 40)):
            with self.assertRaises(KitError):
                release.check_approval(path, revision, commit)
        data = json.loads(path.read_text())
        data["gates"]["prototype_validation"]["status"] = "OPEN"
        path.write_text(json.dumps(data))
        with self.assertRaises(KitError):
            release.check_approval(path, "R1", "a" * 40)

    def test_example_approval_is_no_go(self):
        example = Path(release.__file__).resolve().parents[2] / "manufacturing/approval.example.json"
        with self.assertRaises(KitError):
            release.check_approval(example, "TODO", "TODO_EXACT_COMMIT")

    def test_invalid_revision(self):
        for bad in ("", "../x", "rev 1", "-a"):
            with self.assertRaises(KitError):
                release.export_project(self.fixture_copy("b" + str(abs(hash(bad)))), bad)

    def test_normalized_digest_strips_timestamps(self):
        a, b = self.tmp / "a.gbr", self.tmp / "b.gbr"
        a.write_text("%TF.CreationDate,2026-10-18T09:58:34+02:00*%\nG04 Created by KiCad (PCBNEW 10.0.7) date 2026-10-18 09:58:34*\nX1Y1D01*\n")
        b.write_text("%TF.CreationDate,2027-01-01T00:00:00+00:00*%\nG04 Created by KiCad (PCBNEW 10.0.7) date 2027-01-01 00:00:00*\nX1Y1D01*\n")
        self.assertEqual(release.normalized_digest(a), release.normalized_digest(b))
        b.write_text(b.read_text().replace("X1Y1", "X2Y1"))
        self.assertNotEqual(release.normalized_digest(a), release.normalized_digest(b))


@requires_kicad
class NativeExportTests(TempDirTest):
    def test_draft_exports_complete_and_reproducible(self):
        board = self.fixture_copy()
        first, m1 = release.export_project(board, "A1")
        second, m2 = release.export_project(board, "A2")
        self.assertEqual(first.name, "rev-A1-DRAFT")
        self.assertEqual(m1["decision"], "NO-GO")
        self.assertTrue(m1["exports_complete"], m1["outputs"])
        for path in ("fabrication/drill/divider.drl", "assembly/bom.csv", "assembly/positions.csv",
                     "assembly/assembly-top.pdf", "assembly/assembly-bottom.pdf", "mechanical/board.step",
                     "documentation/schematic.pdf", "documentation/netlist.net", "verification/verification.json"):
            self.assertGreater((first / path).stat().st_size, 0, path)
        gerbers = {p.name for p in (first / "fabrication/gerbers").iterdir()}
        self.assertIn("divider-F_Cu.gtl", gerbers)
        self.assertIn("divider-Edge_Cuts.gm1", gerbers)
        self.assertIn("divider-job.gbrjob", gerbers)
        bom = (first / "assembly/bom.csv").read_text()
        self.assertIn('"R1,R2","10k"', bom)
        self.assertIn("MPN", bom.splitlines()[0])
        for name, entry in m1["artifacts"].items():
            self.assertEqual(len(entry["sha256"]), 64, name)
        comparison = release.compare_manifests(first / "manifest.json", second / "manifest.json")
        self.assertTrue(comparison["identical"], comparison["differences"])
        with self.assertRaises(KitError):
            release.export_project(board, "A1")  # never overwrites an existing revision

    def test_manifest_records_configuration_and_consistency(self):
        board = self.fixture_copy()
        target, manifest = release.export_project(board, "M1", ibom=False)
        self.assertEqual(manifest["kicad_version_status"], "TESTED")
        self.assertEqual(manifest["outputs"]["designator_consistency"], "COMPLETE")
        self.assertEqual(manifest["designator_findings"], [])
        self.assertIn("pin_pad_mapping", manifest["configuration"]["verification"]["gates"])
        self.assertTrue(any("STEP" in item for item in manifest["known_limitations"]))
        from tools.release.exports import release_status

        self.assertEqual(release_status(board)[0]["status"], "CURRENT")

    def test_real_export_becomes_stale_after_source_change(self):
        from tools.release.exports import release_status

        board = self.fixture_copy()
        target, manifest = release.export_project(board, "S1", ibom=False)
        self.assertEqual(manifest["source_hashes"], __import__("tools.core.common", fromlist=["x"]).source_hashes(board))
        self.assertEqual(release_status(board)[0]["status"], "CURRENT")
        pcb = board / "divider.kicad_pcb"
        pcb.write_text(pcb.read_text().replace("(width 0.25)", "(width 0.3)", 1))
        row = release_status(board)[0]
        self.assertEqual(row["status"], "STALE")
        self.assertEqual(row["detail"]["changed_sources"], ["divider.kicad_pcb"])
        # The next export reflects the new state and is CURRENT again; the old one stays STALE.
        release.export_project(board, "S2", ibom=False)
        self.assertEqual({r["release"]: r["status"] for r in release_status(board)},
                         {"rev-S1-DRAFT": "STALE", "rev-S2-DRAFT": "CURRENT"})

    def test_missing_optional_plugin_does_not_block_exports(self):
        board = self.fixture_copy()
        with EnvPatch(KICAD_DOCUMENTS_HOME=str(self.tmp / "no plugins here")):
            _, manifest = release.export_project(board, "P1")
        self.assertEqual(manifest["outputs"]["interactive_html_bom"], "SKIPPED")
        self.assertTrue(manifest["exports_complete"])

    def test_release_requires_explicit_authorization(self):
        board = self.fixture_copy()
        with self.assertRaises(KitError) as ctx:
            release.export_project(board, "R1", approval_file(board))
        self.assertEqual(ctx.exception.exit_code, 22)
        self.assertFalse((board / "manufacturing/releases/generated").exists())

    def test_release_blocked_on_dirty_or_missing_git(self):
        board = self.fixture_copy()
        with self.assertRaises(KitError) as ctx:  # not an independent repository
            release.export_project(board, "R1", approval_file(board), authorize=True)
        self.assertIn("clean Git", str(ctx.exception))

    def test_release_blocked_on_failed_verification(self):
        board = self.fixture_copy()
        pcb = board / "divider.kicad_pcb"
        text = pcb.read_text()
        segment = re.search(r"\n\t\(segment\n.*?\n\t\)", text, re.S)
        pcb.write_text(text[:segment.start()] + text[segment.end():])  # leaves an unconnected net
        approval = approval_file(board)
        with mock.patch.object(release, "git_state", return_value=CLEAN):
            with self.assertRaises(KitError) as ctx:
                release.export_project(board, "R1", approval, authorize=True)
        self.assertIn("release blocked", str(ctx.exception))
        self.assertFalse(list((board / "manufacturing/releases/generated").glob("rev-*")))

    def test_go_release_when_every_gate_passes(self):
        board = self.fixture_copy()
        approval = approval_file(board)
        # Release mode makes metadata/BOM gates blocking; relax them explicitly for this fixture.
        (board / "qa").mkdir(exist_ok=True)
        (board / "qa/verification.json").write_text(json.dumps({"release_gates": [
            "erc", "drc", "schematic_parity", "library_references", "footprint_assignment", "models_3d"]}))
        with mock.patch.object(release, "git_state", return_value=CLEAN):
            target, manifest = release.export_project(board, "R1", approval, authorize=True)
        self.assertEqual(target.name, "rev-R1-GO")
        self.assertEqual(manifest["decision"], "GO")
        self.assertTrue((target / "approval.json").is_file())
        self.assertTrue((target / "evidence/qa/design-reviews/evidence.md").is_file())
        shutil.rmtree(target)
