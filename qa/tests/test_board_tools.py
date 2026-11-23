"""Review tools: Gerber preview parser, mounting sheet, DC power paths, 3D model fit.

Synthetic inputs are tooling cases, not circuits. The DC solver is checked against a closed-form strip
resistance; native cases run KiCad's own Python / kicad-cli on the divider fixture.
"""
import json
import math
from pathlib import Path
import shutil

from kit_test_support import TempDirTest, requires_kicad
from test_board_review import board_text
from tools.core.common import KitError
from tools.quality import gerber_preview, mounting, power_paths

EDGE = """%FSLAX46Y46*%
%MOMM*%
%ADD10C,0.100000*%
D10*
X0Y0D02*
X20000000Y0D01*
X20000000Y-10000000D01*
X0Y-10000000D01*
X0Y0D01*
M02*
"""
COPPER = """%FSLAX46Y46*%
%MOMM*%
%AMRoundRect*
0 comment*
21,1,$1,$2-$3x2,0,0,0*
1,1,$3x2,0,0*%
%ADD10C,0.250000*%
%ADD11R,1.000000X2.000000*%
%ADD12RoundRect,2.000000X1.000000X0.250000*%
D10*
X1000000Y-1000000D02*
X5000000Y-1000000D01*
G75*
G03X7000000Y-3000000I0J-2000000D01*
D11*
X10000000Y-5000000D03*
D12*
X12000000Y-5000000D03*
G36*
X14000000Y-6000000D02*
X16000000Y-6000000D01*
X16000000Y-8000000D01*
X14000000Y-6000000D01*
G37*
M02*
"""
DRILL = """M48
; #@! TF.FileFunction,Plated,1,2,PTH
METRIC
T1C0.300
T2C1.000
%
T1
X10.000Y-5.000
T2
X3.000Y-4.000G85X3.000Y-6.000
M30
"""


class GerberPreviewTests(TempDirTest):
    def package(self):
        pkg = self.tmp / "pkg"
        (pkg / "fabrication/gerbers").mkdir(parents=True)
        (pkg / "fabrication/drill").mkdir(parents=True)
        (pkg / "fabrication/gerbers/board-Edge_Cuts.gm1").write_text(EDGE)
        (pkg / "fabrication/gerbers/board-F_Cu.gtl").write_text(COPPER)
        (pkg / "fabrication/drill/board-PTH.drl").write_text(DRILL)
        return pkg

    def test_macro_arithmetic_without_eval(self):
        self.assertAlmostEqual(gerber_preview.macro_value("$2-$3x2", [2.0, 1.0, 0.25]), 0.5)
        self.assertAlmostEqual(gerber_preview.macro_value("($1+1)/2", [3.0]), 2.0)
        for bad in ("__import__('os')", "$1**2", "[1]"):
            with self.assertRaises(KitError):
                gerber_preview.macro_value(bad, [1.0])

    def test_render_subset_slots_and_mirrored_bottom(self):
        r = gerber_preview.render(self.package(), self.tmp / "out", scale=4)
        self.assertEqual(r["layers"], {"Edge_Cuts": 4, "F_Cu": 5})
        self.assertEqual((r["drill"]["hits"], r["drill"]["slots"]), (1, 1))
        svg = (self.tmp / "out/gerber_F_Cu.svg").read_text()
        self.assertIn("A2.0000,2.0000", svg)                 # G03 arc kept as an arc
        self.assertIn('stroke-width="1.0000" stroke-linecap="round"', (self.tmp / "out/gerber_drill.svg").read_text())
        self.assertEqual(r["png"], bool(shutil.which("rsvg-convert")))

    def test_unsupported_input_stops(self):
        pkg = self.package()
        (pkg / "fabrication/gerbers/board-F_Cu.gtl").write_text(COPPER.replace("M02*", "%SRX2Y2I1J1*%\nM02*"))
        with self.assertRaisesRegex(KitError, "unsupported transform SR"):
            gerber_preview.render(pkg, self.tmp / "out")
        (pkg / "fabrication/gerbers/board-F_Cu.gtl").write_text(COPPER.replace("%MOMM*%", "%MOIN*%"))
        with self.assertRaisesRegex(KitError, "only metric"):
            gerber_preview.render(pkg, self.tmp / "out")
        (pkg / "fabrication/gerbers/board-F_Cu.gtl").write_text(COPPER)
        (pkg / "fabrication/drill/board-PTH.drl").write_text(DRILL.replace("M30", "G00X1Y1\nM30"))
        with self.assertRaisesRegex(KitError, "routed drill"):
            gerber_preview.render(pkg, self.tmp / "out")


MOUNT = """ (footprint "MountingHole:MountingHole_3.2mm_M3" (layer "F.Cu") (at {x} {y} 0)
  (property "Reference" "{ref}")
  (attr exclude_from_pos_files exclude_from_bom)
  (pad "" np_thru_hole circle (at 0 0) (size 3.2 3.2) (drill 3.2) (layers "*.Cu"))
  (zone (net "") (layer "F.Cu") (name "ko") (keepout (tracks not_allowed))
   (polygon (pts (xy {x0} {y0}) (xy {x1} {y0}) (xy {x1} {y1}) (xy {x0} {y1})))))
"""


class MountingTests(TempDirTest):
    def board(self, holes=((14, 14), (86, 56))):
        extra = "".join(MOUNT.format(ref="H%d" % (i + 1), x=x, y=y, x0=x - 4, y0=y - 4, x1=x + 4, y1=y + 4)
                        for i, (x, y) in enumerate(holes))
        text = board_text().replace(" (segment", extra + " (segment", 1)
        text = text.replace('(footprint "Lib:J"', '(footprint "Lib:J"\n  (fp_rect (start -3 -2) (end 3 2) (layer "B.Fab"))', 1)
        path = self.tmp / "board.kicad_pcb"
        path.write_text(text)
        return path

    def test_holes_distances_keepouts_and_bodies(self):
        r = mounting.sheet(self.board(), self.tmp / "out", washer=7.0, bodies=["J1"], title="Fixture")
        self.assertEqual([(h["reference"], h["dx"], h["dy"], h["diameter"]) for h in r["holes"]],
                         [("H1", 4.0, 4.0, 3.2), ("H2", 76.0, 46.0, 3.2)])
        self.assertAlmostEqual(r["distances"][0]["mm"], round(math.hypot(72, 42), 3))
        self.assertEqual((r["page"], r["outline_mm"], r["bodies"]), ("A4", [80.0, 50.0], {"J1": "B.Fab"}))
        svg = (self.tmp / "out/mounting_1to1.svg").read_text()
        self.assertIn('width="297mm" height="210mm"', svg)
        self.assertEqual(svg.count('stroke-dasharray="1,0.7"'), 2)  # footprint keep-outs drawn
        self.assertIn("NOT a drawing release", svg)

    def test_explicit_selection_and_errors(self):
        pcb = self.board()
        self.assertEqual([h["reference"] for h in mounting.sheet(pcb, self.tmp / "a", holes=["H2"])["holes"]], ["H2"])
        with self.assertRaisesRegex(KitError, "Not on the board: H9"):
            mounting.sheet(pcb, self.tmp / "b", holes=["H9"])
        with self.assertRaisesRegex(KitError, "no fab or courtyard"):
            mounting.sheet(pcb, self.tmp / "c", bodies=["R1"])
        big = pcb.read_text().replace("(end 90.0 60.0)", "(end 500.0 60.0)")
        pcb.write_text(big)
        with self.assertRaisesRegex(KitError, "does not fit A3"):
            mounting.sheet(pcb, self.tmp / "d")


def rect(x0, y0, x1, y1):
    return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]


class PowerPathTests(TempDirTest):
    """A 20 x 2 mm strip with 2 x 2 mm terminal pads at both ends: R = rho * 16 mm / (t * 2 mm)."""

    def geo(self, sink_pad=(18, 0, 20, 2), extra_layer=False):
        geo = {"extent": [0, 0, 20, 2], "vias": [],
               "layers": {"F.Cu": {"zones": [rect(0, 0, 20, 2)], "items": []}},
               "pads": [{"ref": "J1", "number": "1", "x": 1, "y": 1, "drill": 0, "shapes": {"F.Cu": rect(0, 0, 2, 2)}},
                        {"ref": "J2", "number": "1", "x": 19, "y": 1, "drill": 0,
                         "shapes": {"F.Cu": rect(*sink_pad)}}]}
        return geo

    def case(self):
        return {"id": "strip", "net": "N", "layers": ["F.Cu"], "source": [["J1", "1"]],
                "sinks": [{"label": "J2", "pads": [["J2", "1"]]}]}

    def test_strip_matches_closed_form(self):
        t = 35e-6
        r = power_paths.solve(self.geo(), self.case(), [2.0], 0.018, {"F.Cu": t}, {"F.Cu": 0.0175}, 0.1, None,
                              (0, 0), self.tmp)
        expected = power_paths.RHO * 16e-3 / (t * 2e-3)               # 3.93 mOhm
        got = r["sinks"][0]["resistance_mohm"] * 1e-3
        self.assertLess(abs(got - expected) / expected, 0.02, (got, expected))
        self.assertAlmostEqual(r["copper_loss_w"], 4 * got, delta=0.02 * 4 * got)
        self.assertTrue((self.tmp / "strip_F_Cu.png").is_file())

    def test_isolated_sink_and_missing_pad(self):
        geo = self.geo(sink_pad=(30, 0, 32, 2))
        geo["extent"] = [0, 0, 32, 2]
        geo["layers"]["F.Cu"]["items"].append(rect(30, 0, 32, 2))
        r = power_paths.solve(geo, self.case(), [1.0], 0.018, {"F.Cu": 35e-6}, {"F.Cu": 0.0175}, 0.1, None,
                              (0, 0), self.tmp)
        self.assertEqual(r["unconnected"], ["J2"])
        case = self.case()
        case["sinks"][0]["pads"] = [["J3", "1"]]
        with self.assertRaisesRegex(KitError, "J3.1 is not on net"):
            power_paths.solve(self.geo(), case, [1.0], 0.018, {"F.Cu": 35e-6}, {"F.Cu": 0.0175}, 0.1, None,
                              (0, 0), self.tmp)

    def test_stackup_and_case_inputs_are_required(self):
        tcu, z = power_paths.stackup('(stackup (layer "F.Cu" (type "copper") (thickness 0.035)) '
                                     '(layer "dielectric 1" (type "core") (thickness 1.5)) '
                                     '(layer "B.Cu" (type "copper") (thickness 0.035)) (copper_finish "HAL"))')
        self.assertAlmostEqual(tcu["B.Cu"], 35e-6)
        self.assertAlmostEqual(z["B.Cu"] - z["F.Cu"], 1.535)
        with self.assertRaisesRegex(KitError, "no stack-up"):
            power_paths.stackup("(kicad_pcb)")
        root = self.fixture_copy()
        with self.assertRaisesRegex(KitError, "No current-path cases"):
            power_paths.analyze(root)
        (root / "hardware/simulations/power").mkdir(parents=True, exist_ok=True)
        (root / "hardware/interfaces").mkdir(parents=True, exist_ok=True)
        (root / "hardware/interfaces/assumptions.json").write_text(json.dumps({"schema": 1, "assumptions": []}))
        (root / "hardware/simulations/power/current-paths.json").write_text(json.dumps(
            {"schema": 1, "cases": [self.case()]}))
        with self.assertRaisesRegex(KitError, "Unresolved assumption reference: None"):
            power_paths.analyze(root)


class PowerPathAnalyzeTests(PowerPathTests):
    """analyze(): currents and plating from assumptions.json, direction sign, evidence (extraction mocked)."""

    def test_currents_come_from_assumptions_with_direction(self):
        from unittest.mock import patch
        root = self.fixture_copy()
        (root / "hardware/interfaces").mkdir(parents=True, exist_ok=True)
        (root / "hardware/simulations/power").mkdir(parents=True, exist_ok=True)
        rec = {"status": "assumed", "source": "synthetic", "revision": "t", "conditions": "tooling test"}
        (root / "hardware/interfaces/assumptions.json").write_text(json.dumps({"schema": 1, "assumptions": [
            dict(rec, id="PLATE", value=0.018, unit="mm"), dict(rec, id="LOAD", value=3.0, unit="A")]}))
        case = self.case()
        case["sinks"][0].update(current="LOAD", direction="in")
        (root / "hardware/simulations/power/current-paths.json").write_text(json.dumps(
            {"schema": 1, "plating": "PLATE", "cases": [case]}))
        with patch.object(power_paths, "extract", return_value=self.geo()), \
                patch.object(power_paths, "stackup", return_value=({"F.Cu": 35e-6}, {"F.Cu": 0.0175})):
            r = power_paths.analyze(root)
        sink = r["results"][0]["sinks"][0]
        self.assertEqual(sink["current_a"], -3.0)
        self.assertGreater(sink["potential_mv"], 0)          # current fed in at the sink: above the source
        self.assertEqual(r["plating_mm"], 0.018)
        self.assertEqual({i["id"] for i in r["basis"]["inputs"]}, {"PLATE", "LOAD"})
        self.assertTrue(Path(r["directory"], "result.json").is_file())


class NativeReviewToolTests(TempDirTest):
    @requires_kicad
    def test_extract_divider_net_and_model_fit(self):
        from tools.core import kicad_env
        from tools.quality import model_fit
        root = self.fixture_copy()
        geo = power_paths.extract(root / "divider.kicad_pcb", "/VOUT", ["F.Cu", "B.Cu"], self.tmp)
        self.assertTrue(geo["pads"] and geo["extent"])
        self.assertTrue(all(p["shapes"] for p in geo["pads"]))
        with self.assertRaisesRegex(KitError, "net /NOPE not on the board"):
            power_paths.extract(root / "divider.kicad_pcb", "/NOPE", ["F.Cu"], self.tmp)
        model = kicad_env.shared_support() / "3dmodels/Resistor_SMD.3dshapes/R_0805_2012Metric.step"
        if not model.is_file():
            self.skipTest("KiCad 3D library not installed")
        before = (root / "divider.kicad_pcb").read_bytes()
        r = model_fit.run_fit(root, "R1", model)
        self.assertEqual(r["status"], "IMAGES_READY")
        self.assertEqual(sorted(r["images"]), ["front", "iso", "left", "top"])
        self.assertEqual((root / "divider.kicad_pcb").read_bytes(), before)
        with self.assertRaisesRegex(KitError, "R9 not on the board"):
            model_fit.run_fit(root, "R9", model)
        failed = [json.loads(p.read_text()) for p in (root / "qa/generated/model-fit").glob("run-*/result.json")]
        self.assertIn("FAILED", {f["status"] for f in failed})
