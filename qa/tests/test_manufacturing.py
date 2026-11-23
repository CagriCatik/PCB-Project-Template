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
    def test_separate_drill_policy_rejects_combined_file(self):
        stage = self.tmp / "export"
        folder = stage / "fabrication/drill"
        folder.mkdir(parents=True)
        self.assertTrue(release.drill_file_consistency(stage, "board"))
        (folder / "board-PTH.drl").write_text("test-only")
        self.assertEqual(release.drill_file_consistency(stage, "board"), [])
        (folder / "board-NPTH.drl").write_text("test-only")
        self.assertEqual(release.drill_file_consistency(stage, "board"), [])
        (folder / "board.drl").write_text("obsolete combined output")
        self.assertTrue(release.drill_file_consistency(stage, "board"))
        plan = {item[0]: item[2] for item in release.export_plan(stage, Path("board.kicad_sch"), Path("board.kicad_pcb"))}
        self.assertIn("--excellon-separate-th", plan["drill"])
        self.assertIn("${DNP}", plan["bom"][plan["bom"].index("--group-by") + 1].split(","))

    def test_view_models_leave_out_restricted_components(self):
        footprints = [
            {"reference": "J1", "models": [{"path": "${KIPRJMOD}/models/vendor/plug.step", "hidden": False}]},
            {"reference": "R1", "models": [{"path": "${KICAD10_3DMODEL_DIR}/R.3dshapes/R.step", "hidden": False}]},
            {"reference": "U1", "models": [{"path": "${KIPRJMOD}/models/vendor/ic.step", "hidden": True},
                                           {"path": "${KIPRJMOD}/models/own/ic.step", "hidden": False}]},
            {"reference": "H1", "models": []},
        ]
        with mock.patch("tools.kicad.design.board_footprints", return_value=footprints):
            self.assertEqual(release.view_components("b.kicad_pcb", ["*/vendor/*"]), (["R1", "U1"], ["J1"]))
            self.assertEqual(release.view_components("b.kicad_pcb", []), (["J1", "R1", "U1"], []))
        stage = self.tmp / "export"
        plans = {refs: {i[0]: i[2] for i in release.export_plan(stage, Path("b.kicad_sch"), Path("b.kicad_pcb"), refs)}
                 for refs in (None, ("R1", "U1"), ())}
        self.assertNotIn("--component-filter", plans[None]["view_glb"])
        self.assertNotIn("--no-components", plans[None]["view_stl"])
        glb = plans[("R1", "U1")]["view_glb"]
        self.assertEqual(glb[glb.index("--component-filter") + 1], "R1,U1")
        self.assertIn("--no-components", plans[()]["view_stl"])
        for plan in plans.values():
            self.assertIn("--no-dnp", plan["view_glb"])
            self.assertNotIn("--include-tracks", plan["view_glb"])
            self.assertNotIn("--component-filter", plan["step"])

    def test_restricted_model_patterns_must_be_strings(self):
        from tools.quality.verification import load_config

        root = self.tmp / "p"
        (root / "qa").mkdir(parents=True)
        self.assertEqual(load_config(root)["restricted_3d_models"], [])
        (root / "qa/verification.json").write_text('{"restricted_3d_models": ["*/vendor/*"]}')
        self.assertEqual(load_config(root)["restricted_3d_models"], ["*/vendor/*"])
        for bad in ('"*/vendor/*"', '[""]', "[1]"):
            (root / "qa/verification.json").write_text('{"restricted_3d_models": %s}' % bad)
            with self.assertRaises(KitError):
                load_config(root)

    def test_glb_digest_ignores_export_time_and_buffer_order(self):
        import struct

        def glb(doc, buffer):
            js = json.dumps(doc).encode()
            js += b" " * (-len(js) % 4)
            body = struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(buffer), b"BIN\0") + buffer
            return b"glTF" + struct.pack("<II", 2, 12 + len(body)) + body

        doc = {"asset": {"version": "2.0", "extras": {"generated_at": "T1", "pcb_name": "a"}},
               "nodes": [{"name": "R1", "mesh": 0}], "meshes": [{"name": "R"}]}
        later = json.loads(json.dumps(doc))
        later["asset"]["extras"] = {"generated_at": "T2", "pcb_name": "b"}
        other = json.loads(json.dumps(doc))
        other["nodes"].append({"name": "R2", "mesh": 0})
        paths = []
        for k, (d, buf) in enumerate(((doc, b"\0\1\2\3"), (later, b"\3\2\1\0"), (other, b"\0\1\2\3"))):
            paths.append(self.tmp / ("m%d.glb" % k))
            paths[-1].write_bytes(glb(d, buf))
        digests = [release.normalized_digest(p) for p in paths]
        self.assertEqual(digests[0]["method"], "glb-structure")
        self.assertEqual(digests[0], digests[1])
        self.assertNotEqual(digests[0], digests[2])

    def test_mixed_dnp_bom_row_is_rejected_even_when_references_match(self):
        stage = self.tmp / "export"
        asm = stage / "assembly"
        asm.mkdir(parents=True)
        (asm / "positions.csv").write_text("Ref\nR1\n")
        symbols = [{"reference": ref, "dnp": dnp, "power": False, "in_bom": True, "on_board": True}
                   for ref, dnp in (("R1", False), ("R2", True))]
        footprints = [{"reference": "R1", "attributes": []}, {"reference": "R2", "attributes": ["dnp"]}]
        with mock.patch("tools.kicad.design.schematic_symbols", return_value={"symbols": symbols}), \
                mock.patch("tools.kicad.design.board_footprints", return_value=footprints):
            (asm / "bom.csv").write_text('Refs,DNP\n"R1,R2",DNP\n')
            findings = release.designator_consistency(stage, (None, None, None))
            self.assertEqual(findings, [{"problem": "BOM DNP state differs from schematic", "reference": "R1"}])
            (asm / "bom.csv").write_text("Refs,DNP\nR1,\nR2,DNP\n")
            self.assertEqual(release.designator_consistency(stage, (None, None, None)), [])
            (asm / "bom.csv").write_text("Refs\nR1\nR2\n")
            self.assertTrue(release.designator_consistency(stage, (None, None, None)))

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
        for path in ("fabrication/drill/divider-PTH.drl", "assembly/bom.csv", "assembly/positions.csv",
                     "assembly/assembly-top.pdf", "assembly/assembly-bottom.pdf", "mechanical/board.step",
                     "mechanical/board-view.glb", "mechanical/board-view.stl",
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
