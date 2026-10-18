"""Component records: creation, schema and reference validation."""

import hashlib
import json

from kit_test_support import NATIVE, TempDirTest
from tools.project import components
from tools.project import templates as template_engine
from tools.core.common import KitError


class ComponentTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.project, _ = template_engine.create("generic-pcb", self.tmp / "parts project", "parts", register=False)

    def write(self, data):
        path = components.record_path(self.project, data["manufacturer"], data["mpn"])
        path.write_text(json.dumps(data))
        return path

    def test_add_creates_candidate_and_never_overwrites(self):
        path = components.add(self.project, "Test Maker", "TM-1/A", "Device:R", "Resistor_SMD:R_0805_2012Metric")
        self.assertEqual(path.name, "Test-Maker__TM-1-A.json")
        data = json.loads(path.read_text())
        self.assertEqual(data["approval"]["status"], "candidate")
        path.write_text(path.read_text().replace('"description": ""', '"description": "edited"'))
        with self.assertRaises(KitError):
            components.add(self.project, "Test Maker", "TM-1/A")
        self.assertIn("edited", path.read_text())

    def test_required_identity(self):
        with self.assertRaises(KitError):
            components.add(self.project, " ", "X")

    def test_detects_missing_and_broken_references(self):
        data = components.template_record("Test Maker", "TM-2")
        data["kicad"].update({"symbol": "NoSuchLib:R", "footprint": "Resistor_SMD:NoSuchFootprint",
                              "model_3d": "${KICAD10_3DMODEL_DIR}/nope.step"})
        data["datasheet"].update({"url": "http://insecure.invalid/ds.pdf", "local_file": "components/datasheets/x.pdf"})
        self.write(data)
        problems = " | ".join(f["problem"] for f in components.validate(self.project)["findings"])
        self.assertIn("NoSuchLib:R", problems)
        self.assertIn("datasheet local_file missing", problems)
        self.assertIn("model_3d not found", problems)
        if NATIVE:
            self.assertIn("footprint not found in library", problems)

    def test_datasheet_hash_mismatch(self):
        ds = self.project / "components/datasheets/tm3.pdf"
        ds.write_bytes(b"%PDF-1.4 test-only bytes")
        data = components.template_record("Test Maker", "TM-3")
        data["datasheet"].update({"local_file": "components/datasheets/tm3.pdf", "sha256": "0" * 64})
        self.write(data)
        findings = components.validate(self.project)["findings"]
        self.assertTrue(any("sha256 mismatch" in f["problem"] for f in findings))
        data["datasheet"]["sha256"] = hashlib.sha256(ds.read_bytes()).hexdigest()
        self.write(data)
        findings = components.validate(self.project)["findings"]
        self.assertFalse(any("sha256" in f["problem"] for f in findings))

    def test_approval_requires_evidence(self):
        data = components.template_record("Test Maker", "TM-4")
        data["approval"]["status"] = "approved"
        self.write(data)
        problems = " | ".join(f["problem"] for f in components.validate(self.project)["findings"])
        for needed in ("approved_by", "datasheet.revision", "ratings", "procurement", "approval.date"):
            self.assertIn(needed, problems)

    def test_invalid_status_duplicate_and_bad_json(self):
        data = components.template_record("Test Maker", "TM-5")
        data["approval"]["status"] = "maybe"
        self.write(data)
        dup = dict(data, mpn="tm-5")
        (self.project / components.PART_DIR / "copy.json").write_text(json.dumps(dup))
        (self.project / components.PART_DIR / "broken.json").write_text("{not json")
        result = components.validate(self.project)
        problems = " | ".join(f["problem"] for f in result["findings"])
        self.assertIn("approval.status must be", problems)
        self.assertIn("duplicate of", problems)
        self.assertIn("unreadable JSON", problems)
        self.assertIn("file name should be", problems)
        self.assertEqual(result["status"], "FAIL")

    def test_empty_project_passes(self):
        self.assertEqual(components.validate(self.project)["status"], "PASS")
