"""Template hardening: board profiles, portability and relocation, pin/pad mapping,
KiCad version policy, release staleness and designator consistency."""

import json
from pathlib import Path
import shutil
import stat

from kit_test_support import FIXTURES, ROOT, EnvPatch, TempDirTest, requires_kicad
from tools.core.common import KitError, source_hashes
from tools.kicad import portability
from tools.project import profiles
from tools.project import templates as template_engine
from tools.quality.verification import verify
from tools.release import exports

CUSTOM = FIXTURES / "custom-lib"


def fake_cli(folder, version):
    path = folder / "kicad-cli"
    path.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo '%s'; exit 0; fi\nexit 1\n" % version)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ProfileTests(TempDirTest):
    def test_profiles_are_consistent(self):
        found = profiles.profiles()
        self.assertEqual(set(found), {"2-layer", "4-layer"})
        for pid, data in found.items():
            self.assertAlmostEqual(profiles.board_thickness(data), 1.6, places=6)
            self.assertIn("example", data["description"].lower())
            pro, pcb = profiles.default_files(pid)
            settings = json.loads(pro.read_text())
            rules = settings["board"]["design_settings"]["rules"]
            for key, value in data["rules"].items():
                self.assertAlmostEqual(rules[key], value, places=6, msg=key)
            classes = {c["name"]: c for c in settings["net_settings"]["classes"]}
            for c in data["netclasses"]:
                self.assertAlmostEqual(classes[c["name"]]["track_width"], c["track_width"], places=6)
            text = pcb.read_text()
            self.assertIn("(stackup", text)
            self.assertEqual(text.count('(type "copper")'), data["copper_layers"])
            self.assertIn('(title "${PROJECTNAME}")', text)

    def test_invalid_profile_rejected(self):
        bad = self.tmp / "profiles"
        bad.mkdir()
        data = json.loads((profiles.PROFILE_DIR / "4-layer.json").read_text())
        data["copper_layers"] = 2
        (bad / "broken.json").write_text(json.dumps(data))
        original = profiles.PROFILE_DIR
        profiles.PROFILE_DIR = bad
        try:
            with self.assertRaises(KitError):
                profiles.profiles()
        finally:
            profiles.PROFILE_DIR = original

    def test_create_with_profile(self):
        path, record = template_engine.create("stm32-embedded", self.tmp / "Vier Lagen ä" / "Board", "Board",
                                              register=False, profile_id="4-layer")
        self.assertEqual(record["profile"], "4-layer")
        pcb = (path / "Board.kicad_pcb").read_text()
        self.assertIn('"In1.Cu"', pcb)
        self.assertIn('"In2.Cu"', pcb)
        sch = (path / "Board.kicad_sch").read_text()
        self.assertIn('(title "${PROJECTNAME}")', sch)
        self.assertTrue((path / "docs/engineering/routing-guidelines.md").is_file())
        with self.assertRaises(KitError):
            template_engine.create("generic-pcb", self.tmp / "x", "x", register=False, profile_id="6-layer")
        default, rec = template_engine.create("generic-pcb", self.tmp / "y", "y", register=False)
        self.assertEqual(rec["profile"], "2-layer")
        self.assertNotIn('"In1.Cu"', (default / "y.kicad_pcb").read_text())

    @requires_kicad
    def test_kicad_reads_profiles_back(self):
        for pid in ("2-layer", "4-layer"):
            path, _ = template_engine.create("generic-pcb", self.tmp / pid, "p" + pid[0], register=False,
                                             profile_id=pid)
            back = profiles.inspect(path / ("p%s.kicad_pcb" % pid[0]))
            data = profiles.get_profile(pid)
            self.assertEqual(back["copper_layers"], data["copper_layers"])
            self.assertTrue(back["has_stackup"])
            self.assertAlmostEqual(back["min_track_width"], data["rules"]["min_track_width"], places=6)
            self.assertEqual(set(back["netclasses"]), {c["name"] for c in data["netclasses"]})
            result = verify(path)
            failing = {g: [f.get("type") for f in r["findings"]] for g, r in result["gates"].items()
                       if r["status"] != "PASS"}
            # A blank board has no outline yet: that, and only that, must be reported.
            self.assertEqual(failing, {"drc": ["invalid_outline"]})

    @requires_kicad
    def test_rebuilt_profiles_match_committed_defaults(self):
        for pid in profiles.profiles():
            fresh = profiles.build(pid, self.tmp / pid)
            committed = profiles.inspect(profiles.default_files(pid)[1])
            self.assertEqual(fresh, committed)


class PortabilityTests(TempDirTest):
    def test_classification(self):
        ok = ["${KIPRJMOD}/hardware/libraries/x.pretty", "${KICAD10_3DMODEL_DIR}/R.3dshapes/R.step", "", None]
        for value in ok:
            self.assertIsNone(portability.classify(value), value)
        for value, word in (("/Users/me/lib.pretty", "absolute"), ("~/lib", "absolute"), ("C:\\lib", "absolute"),
                            ("${KICAD9_3DMODEL_DIR}/x.wrl", "legacy"), ("${MY_LIBS}/x.pretty", "user-defined")):
            self.assertIn(word, portability.classify(value), value)

    def test_custom_library_project_is_portable(self):
        self.assertEqual(portability.check(self.fixture_copy("cl", CUSTOM)), [])

    def test_absolute_paths_are_reported(self):
        project = self.fixture_copy("cl", CUSTOM)
        table = project / "fp-lib-table"
        table.write_text(table.read_text().replace("${KIPRJMOD}", str(project)))
        pcb = project / "custom-lib.kicad_pcb"
        pcb.write_text(pcb.read_text().replace("${KICAD10_3DMODEL_DIR}", "/Users/someone/models", 1))
        pro = project / "custom-lib.kicad_pro"
        data = json.loads(pro.read_text())
        data["schematic"] = dict(data.get("schematic", {}), page_layout_descr_file="/Users/someone/sheet.kicad_wks")
        pro.write_text(json.dumps(data))
        problems = {(Path(f["file"]).name.split()[0], f["problem"]) for f in portability.check(project)}
        self.assertIn(("fp-lib-table", "absolute path"), problems)
        self.assertIn(("custom-lib.kicad_pcb", "absolute path"), problems)
        self.assertIn(("custom-lib.kicad_pro", "user home directory path in project settings"), problems)

    def test_broken_footprint_library_path(self):
        project = self.fixture_copy("cl", CUSTOM)
        shutil.move(str(project / "hardware/libraries/footprints"), str(project / "hardware/libraries/moved"))
        result = verify(project, gates=["library_references"], cli=_NoCli())
        self.assertEqual(result["gates"]["library_references"]["status"], "FAIL")
        self.assertIn("footprint library directory missing", json.dumps(result["gates"]["library_references"]))

    def test_pin_without_pad_is_detected(self):
        project = self.fixture_copy("cl", CUSTOM)
        sch = project / "custom-lib.kicad_sch"
        sch.write_text(sch.read_text().replace('"Resistor_SMD:R_0805_2012Metric"',
                                               '"Project_Footprints:TestPoint_Pad_D1.5mm"', 1))
        result = verify(project, gates=["pin_pad_mapping"], cli=_NoCli())
        gate = result["gates"]["pin_pad_mapping"]
        self.assertEqual(gate["status"], "FAIL")
        self.assertIn("R1", json.dumps(gate["findings"]))
        self.assertIn("without a pad: 2", json.dumps(gate["findings"]))

    @requires_kicad
    def test_relocation_keeps_project_valid(self):
        first = self.fixture_copy("first location", CUSTOM)
        gates = ["erc", "drc", "schematic_parity", "library_references", "portability", "pin_pad_mapping"]
        self.assertEqual(verify(first, gates=gates)["quality_gate"], "PASS")
        moved = self.tmp / "Zweiter Ort – Prüfung" / "relocated board"
        moved.parent.mkdir()
        shutil.move(str(first), str(moved))
        result = verify(moved, gates=gates)
        self.assertEqual(result["quality_gate"], "PASS", result["blocking"])

    @requires_kicad
    def test_missing_3d_model_is_reported_not_invented(self):
        result = verify(self.fixture_copy("cl", CUSTOM), gates=["models_3d"])
        refs = {f["reference"] for f in result["gates"]["models_3d"]["findings"]}
        self.assertEqual(refs, {"TP1", "TP2"})


class _NoCli:
    """Stand-in for gates that never call kicad-cli (library/pin checks)."""

    version, version_status, version_record = "10.0.7", "TESTED", {}


class VersionPolicyTests(TempDirTest):
    def test_untested_version_requires_opt_in_and_is_marked(self):
        from tools.kicad.cli import KiCadCLI

        cli = fake_cli(self.tmp, "10.0.8")
        with EnvPatch(KICAD_CLI=str(cli), KICAD_KIT_ALLOW_UNTESTED=None):
            with self.assertRaises(KitError) as ctx:
                KiCadCLI()
            self.assertEqual(ctx.exception.exit_code, 11)
        with EnvPatch(KICAD_CLI=str(cli), KICAD_KIT_ALLOW_UNTESTED="1"):
            self.assertEqual(KiCadCLI().version_status, "UNTESTED")
        with EnvPatch(KICAD_CLI=str(fake_cli(self.tmp, "not a version")), KICAD_KIT_ALLOW_UNTESTED="1"):
            with self.assertRaises(KitError):
                KiCadCLI()

    def test_untested_version_blocks_go_release(self):
        from test_manufacturing import approval_file

        board = self.fixture_copy()
        approval = approval_file(board)
        with EnvPatch(KICAD_CLI=str(fake_cli(self.tmp, "10.0.8")), KICAD_KIT_ALLOW_UNTESTED="1"):
            with self.assertRaises(KitError) as ctx:
                exports.export_project(board, "R1", approval, authorize=True)
        self.assertEqual(ctx.exception.exit_code, 22)
        self.assertIn("untested", str(ctx.exception))
        self.assertFalse((board / "manufacturing/releases/generated").exists())


class ReleaseIntegrityTests(TempDirTest):
    def test_expand_reference_ranges(self):
        self.assertEqual(exports.expand_refs("R1,R3-R5"), ["R1", "R3", "R4", "R5"])
        self.assertEqual(exports.expand_refs("C10-C12, J1"), ["C10", "C11", "C12", "J1"])
        self.assertEqual(exports.expand_refs(""), [])

    def stage(self, project, bom_refs, pos_refs):
        stage = self.tmp / ("stage-%d" % len(list(self.tmp.iterdir())))
        (stage / "assembly").mkdir(parents=True)
        (stage / "assembly/bom.csv").write_text('"Refs","Value"\n' + "".join('"%s","x"\n' % r for r in bom_refs))
        (stage / "assembly/positions.csv").write_text("Ref,Val\n" + "".join('"%s","x"\n' % r for r in pos_refs))
        files = [project / ("divider." + e) for e in ("kicad_pro", "kicad_sch", "kicad_pcb")]
        return exports.designator_consistency(stage, files)

    def test_designator_consistency(self):
        project = self.fixture_copy()
        self.assertEqual(self.stage(project, ["J1", "R1,R2"], ["J1", "R1", "R2"]), [])
        findings = self.stage(project, ["J1", "R1-R3"], ["J1", "R1", "R1"])
        text = json.dumps(findings)
        self.assertIn("BOM has extra", text)                   # R3 is not in the schematic
        self.assertIn("lists a designator twice", text)        # R1 twice in the placement file
        self.assertIn("position file is missing", text)        # R2 not placed
        self.assertEqual(self.stage(project, [], [])[0]["problem"], "BOM is missing")

    def fake_release(self, project, name="rev-A-DRAFT"):
        folder = project / "manufacturing/releases/generated" / name
        (folder / "assembly").mkdir(parents=True)
        (folder / "assembly/bom.csv").write_text("x\n")
        from tools.core.common import sha256

        (folder / "manifest.json").write_text(json.dumps({
            "decision": "NO-GO", "created": "now", "source_hashes": source_hashes(project),
            "artifacts": {"assembly/bom.csv": {"sha256": sha256(folder / "assembly/bom.csv")}}}))
        return folder

    def test_release_status_detects_stale_and_modified(self):
        project = self.fixture_copy()
        folder = self.fake_release(project)
        (project / "manufacturing/releases/generated/rev-B-DRAFT").mkdir()
        status = {r["release"]: r["status"] for r in exports.release_status(project)}
        self.assertEqual(status, {"rev-A-DRAFT": "CURRENT", "rev-B-DRAFT": "INCOMPLETE"})
        (project / "divider.kicad_sch").write_text((project / "divider.kicad_sch").read_text() + "\n")
        row = exports.release_status(project)[0]
        self.assertEqual(row["status"], "STALE")
        self.assertEqual(row["detail"]["changed_sources"], ["divider.kicad_sch"])
        (folder / "assembly/bom.csv").write_text("edited by hand\n")
        self.assertEqual(exports.release_status(project)[0]["status"], "MODIFIED")
        from tools.cli.main import main

        self.assertEqual(main(["releases", str(project)]), 21)


class RepositoryIntegrityTests(TempDirTest):
    def test_all_configuration_files_parse(self):
        skip = {".git", ".venv", "generated", "archive", "__pycache__"}
        files = [p for p in ROOT.rglob("*.json") if not skip & set(p.relative_to(ROOT).parts)]
        self.assertGreater(len(files), 10)
        for path in files:
            with self.subTest(path=str(path.relative_to(ROOT))):
                json.loads(path.read_text())
        for entry in json.loads((ROOT / "meta/templates/skeleton.json").read_text())["copy"]:
            self.assertTrue((ROOT / entry["from"]).exists(), entry["from"])

    def test_relative_documentation_links_resolve(self):
        import re

        docs = [ROOT / "README.md", ROOT / "qa/fixtures/README.md"] + sorted((ROOT / "docs").glob("*.md")) + \
            sorted((ROOT / "docs/engineering").glob("*.md"))
        for doc in docs:
            for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", doc.read_text()):
                if "://" in target or target.startswith("mailto:"):
                    continue
                with self.subTest(doc=doc.name, link=target):
                    self.assertTrue((doc.parent / target).exists(), "%s -> %s" % (doc.name, target))

    def test_malformed_kicad_reports_are_never_a_pass(self):
        from tools.kicad.cli import summarize_drc, summarize_erc

        for bad in (None, {}, {"sheets": "x"}, {"sheets": [{"no_violations": []}]}):
            self.assertFalse(summarize_erc(bad)["valid"])
        for bad in (None, {"violations": []}, {"violations": [], "unconnected_items": [], "schematic_parity": None}):
            self.assertFalse(summarize_drc(bad)["valid"])
        excluded = summarize_erc({"sheets": [{"violations": [{"severity": "exclusion"}, {"severity": "error"}]}]})
        self.assertEqual((len(excluded["active"]), len(excluded["excluded"])), (1, 1))
