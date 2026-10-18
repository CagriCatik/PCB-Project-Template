"""Quality gates on the genuine KiCad fixture and deliberately broken variants."""

import json
import re

from kit_test_support import TempDirTest, requires_kicad
from tools.project import components
from tools.kicad import design
from tools.core.common import KitError, source_hashes
from tools.quality.verification import load_config, verify


def add_fields(sch_path, values):
    """Insert Manufacturer/MPN properties (test-only data) after each Datasheet property."""
    text = sch_path.read_text()
    for ref, (mfr, mpn) in values.items():
        block = re.search(r'\(property "Reference" "%s".*?\(property "Datasheet"' % ref, text, re.S)
        insert = block.end() - len('(property "Datasheet"')
        extra = ('(property "Manufacturer" "%s"\n\t\t\t(at 0 0 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t'
                 '(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)\n\t\t\t)\n\t\t)\n\t\t(property "MPN" "%s"\n\t\t\t'
                 '(at 0 0 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t\t(hide yes)'
                 '\n\t\t\t)\n\t\t)\n\t\t') % (mfr, mpn)
        text = text[:insert] + extra + text[insert:]
    text = text.replace('(property "Datasheet" "~"', '(property "Datasheet" "https://example.invalid/test-only.pdf"')
    sch_path.write_text(text)


class OfflineGateTests(TempDirTest):
    def test_design_model_reads_fixture(self):
        board = self.fixture_copy()
        model = design.schematic_symbols(board / "divider.kicad_sch")
        self.assertEqual([s["reference"] for s in model["symbols"]], ["J1", "R1", "R2"])
        fps = design.board_footprints(board / "divider.kicad_pcb")
        self.assertEqual([f["reference"] for f in fps], ["J1", "R1", "R2"])
        self.assertTrue(all(f["models"] for f in fps))

    def test_invalid_gate_configuration(self):
        board = self.fixture_copy()
        (board / "qa").mkdir(exist_ok=True)
        (board / "qa/verification.json").write_text(json.dumps({"gates": {"erc": "sometimes"}}))
        with self.assertRaises(KitError):
            load_config(board)


@requires_kicad
class NativeGateTests(TempDirTest):
    def test_fixture_passes_required_gates_and_flags_advisory(self):
        board = self.fixture_copy()
        before = source_hashes(board)
        result = verify(board)
        self.assertEqual(result["quality_gate"], "PASS", result["blocking"])
        for gate in ("erc", "drc", "schematic_parity", "library_references", "footprint_assignment", "models_3d"):
            self.assertEqual(result["gates"][gate]["status"], "PASS", gate)
        # No MPNs in the fixture: advisory gates must say so, not pass silently.
        self.assertEqual(result["gates"]["component_metadata"]["status"], "FAIL")
        self.assertEqual(set(result["warnings"]), {"component_metadata", "bom"})
        self.assertTrue(result["source_unchanged"])
        self.assertEqual(before, source_hashes(board))
        self.assertFalse(result["fabrication_approval"])

    def test_release_mode_makes_advisory_gates_blocking(self):
        result = verify(self.fixture_copy(), release=True)
        self.assertEqual(result["quality_gate"], "FAIL")
        self.assertIn("component_metadata", result["blocking"])

    def test_removed_track_is_unconnected(self):
        board = self.fixture_copy()
        pcb = board / "divider.kicad_pcb"
        text = pcb.read_text()
        first_segment = re.search(r"\n\t\(segment\n.*?\n\t\)", text, re.S)
        pcb.write_text(text[:first_segment.start()] + text[first_segment.end():])
        result = verify(board, gates=["drc"])
        self.assertEqual(result["gates"]["drc"]["status"], "FAIL")
        self.assertGreaterEqual(result["gates"]["drc"]["unconnected"], 1)
        self.assertEqual(result["quality_gate"], "FAIL")

    def test_corrupt_schematic_is_an_error_not_a_pass(self):
        board = self.fixture_copy()
        (board / "divider.kicad_sch").write_text("(kicad_sch (version 20260306)")
        result = verify(board)
        self.assertIn(result["gates"]["erc"]["status"], ("ERROR", "FAIL"))
        self.assertEqual(result["quality_gate"], "FAIL")

    def test_broken_library_reference(self):
        board = self.fixture_copy()
        sch = board / "divider.kicad_sch"
        sch.write_text(sch.read_text().replace('(lib_id "Device:R")', '(lib_id "Missing_Lib:R")', 1))
        result = verify(board, gates=["library_references"])
        findings = result["gates"]["library_references"]["findings"]
        self.assertEqual(result["gates"]["library_references"]["status"], "FAIL")
        self.assertIn("Missing_Lib:R", json.dumps(findings))

    def test_missing_footprint_and_3d_model(self):
        board = self.fixture_copy()
        sch = board / "divider.kicad_sch"
        sch.write_text(sch.read_text().replace('"Resistor_SMD:R_0805_2012Metric"', '""', 1))
        pcb = board / "divider.kicad_pcb"
        pcb.write_text(pcb.read_text().replace("R_0805_2012Metric.step", "R_0805_DOES_NOT_EXIST.step", 1))
        result = verify(board, gates=["footprint_assignment", "models_3d"])
        self.assertEqual(result["gates"]["footprint_assignment"]["count"], 1)
        self.assertEqual(result["gates"]["models_3d"]["status"], "FAIL")

    def test_metadata_and_bom_pass_with_approved_records(self):
        board = self.fixture_copy()
        refs = {"J1": ("Test Maker", "TEST-ONLY-J"), "R1": ("Test Maker", "TEST-ONLY-R"),
                "R2": ("Test Maker", "TEST-ONLY-R")}
        add_fields(board / "divider.kicad_sch", refs)
        footprints = {"TEST-ONLY-J": ("Connector_Generic:Conn_01x03",
                                      "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical"),
                      "TEST-ONLY-R": ("Device:R", "Resistor_SMD:R_0805_2012Metric")}
        (board / components.PART_DIR).mkdir(parents=True)
        for mpn, (symbol, footprint) in footprints.items():
            data = components.template_record("Test Maker", mpn)
            data["kicad"].update({"symbol": symbol, "footprint": footprint})
            data["datasheet"].update({"url": "https://example.invalid/test-only.pdf", "revision": "test"})
            data["ratings"] = {"test_only": {"value": 0, "unit": "n/a", "source": "unit test"}}
            data["procurement"] = [{"supplier": "test", "lifecycle": "unknown"}]
            data["approval"] = {"status": "approved", "approved_by": "unit test", "date": "2026-01-01"}
            components.record_path(board, "Test Maker", mpn).write_text(json.dumps(data))
        result = verify(board, gates=["component_metadata", "bom"])
        self.assertEqual(result["gates"]["component_metadata"]["status"], "PASS",
                         result["gates"]["component_metadata"]["findings"])
        self.assertEqual(result["gates"]["bom"]["status"], "PASS", result["gates"]["bom"]["findings"])
        # A record whose footprint disagrees with the schematic is caught.
        path = components.record_path(board, "Test Maker", "TEST-ONLY-R")
        data = json.loads(path.read_text())
        data["kicad"]["footprint"] = "Resistor_SMD:R_0603_1608Metric"
        path.write_text(json.dumps(data))
        result = verify(board, gates=["bom"])
        self.assertIn("differs from record", json.dumps(result["gates"]["bom"]["findings"]))

    def test_open_editor_lock_blocks_automation(self):
        board = self.fixture_copy()
        (board / "~divider.kicad_sch.lck").write_text("{}")
        with self.assertRaises(KitError) as ctx:
            verify(board)
        self.assertEqual(ctx.exception.exit_code, 14)
