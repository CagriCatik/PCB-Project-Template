"""Read-only board review checks: board model, copper/placement diff, fabrication package geometry.

Synthetic boards and packages are tooling inputs, not circuits. The native cases export the divider fixture
with the pinned KiCad and must agree with the board model exactly.
"""
import csv
import io
import json
import re
from contextlib import redirect_stdout
from pathlib import Path

from kit_test_support import TempDirTest, requires_kicad
from tools.quality import board_model as boardmodel
from tools.quality import board_diff, fab_check

BOARD = """(kicad_pcb (version 20241229) (generator "pcbnew")
 (general (thickness 1.6))
 (layers (0 "F.Cu" signal) (2 "B.Cu" signal) (25 "Edge.Cuts" user))
 (setup (aux_axis_origin {ax} {ay}))
 (gr_rect (start {x0} {y0}) (end {x1} {y1}) (layer "Edge.Cuts"))
 (footprint "Lib:R" (layer "F.Cu") (at {fx} {fy} 90)
  (property "Reference" "R1")
  (attr smd)
  (pad "1" smd rect (at -1 0) (size 1 1) (layers "F.Cu") (net "A"))
  (pad "2" smd rect (at 1 0) (size 1 1) (layers "F.Cu") (net "B")))
 (footprint "Lib:J" (layer "B.Cu") (at {jx} {jy} 180)
  (property "Reference" "J1")
  (attr through_hole)
  (pad "1" thru_hole circle (at 2.54 0) (size 1.7 1.7) (drill 1.0) (layers "*.Cu") (net "A"))
  (pad "" np_thru_hole circle (at 0 3) (size 3 3) (drill 3) (layers "*.Cu")))
 (footprint "Lib:DNP" (layer "F.Cu") (at {dx} {jy} 0)
  (property "Reference" "R2")
  (attr smd dnp)
  (pad "1" smd rect (at 0 0) (size 1 1) (layers "F.Cu") (net "B")))
 (segment (start {s0x} {s0y}) (end {s1x} {s1y}) (width 0.25) (layer "F.Cu") (net "A"))
 {extra}
 (via (at {vx} {vy}) (size 0.6) (drill 0.3) (layers "F.Cu" "B.Cu") (net "A"))
 (zone (net "B") (layer "B.Cu") (name "pour") (priority 1) (connect_pads (clearance 0.2))
  (polygon (pts (xy {x0} {y0}) (xy {zx} {y0}) (xy {zx} {zy}) (xy {x0} {zy}))))
)
"""


def board_text(dx=0.0, dy=0.0, extra="", r1=(30, 20), ax=0.0, ay=0.0, zx=60):
    v = {"x0": 10, "y0": 10, "x1": 90, "y1": 60, "fx": r1[0], "fy": r1[1], "jx": 50, "jy": 40,
         "s0x": 31, "s0y": 20, "s1x": 50, "s1y": 20, "vx": 50, "vy": 20, "zx": zx, "zy": 30}
    for k in list(v):
        if k in ("fx", "jx", "s0x", "s1x", "vx", "x0", "x1", "zx"):
            v[k] = v[k] + dx
        elif k in ("fy", "jy", "s0y", "s1y", "vy", "y0", "y1", "zy"):
            v[k] = v[k] + dy
    v["fx"], v["fy"] = r1[0] + dx, r1[1] + dy
    v["dx"] = 70 + dx
    return BOARD.format(extra=extra, ax=ax, ay=ay, **v)


class BoardModelTests(TempDirTest):
    def write(self, name, text):
        path = self.tmp / name
        path.write_text(text)
        return path

    def test_absolute_pads_attributes_holes(self):
        b = boardmodel.load(self.write("a.kicad_pcb", board_text()))
        self.assertEqual(b["outline_bbox"], (10.0, 10.0, 90.0, 60.0))
        r1 = {p["number"]: (round(p["x"], 6), round(p["y"], 6)) for p in b["footprints"]["R1"]["pads"]}
        # 90 deg counter-clockwise on screen (y down): local (-1, 0) -> (0, +1)
        self.assertEqual(r1, {"1": (30.0, 21.0), "2": (30.0, 19.0)})
        self.assertEqual(b["footprints"]["J1"]["side"], "bottom")
        self.assertTrue(b["footprints"]["R2"]["dnp"])
        holes = sorted((k, d, round(x, 6), round(y, 6)) for k, d, x, y, _ in boardmodel.holes(b))
        self.assertEqual(holes, [("N", 3.0, 50.0, 37.0), ("P", 0.3, 50.0, 20.0), ("P", 1.0, 47.46, 40.0)])


class BoardDiffTests(TempDirTest):
    def pair(self, before, after):
        a, b = self.tmp / "before.kicad_pcb", self.tmp / "after.kicad_pcb"
        a.write_text(before)
        b.write_text(after)
        return a, b

    def test_identical_and_translated_boards_compare_equal(self):
        a, b = self.pair(board_text(), board_text(dx=7.5, dy=-3.25))
        r = board_diff.compare(a, b)
        self.assertEqual(r["status"], "NO_CHANGES", r)

    def test_changes_listed_and_region_classification(self):
        extra = '(segment (start 70 50) (end 80 50) (width 0.25) (layer "B.Cu") (net "B"))'
        a, b = self.pair(board_text(), board_text(extra=extra, r1=(32, 20)))
        r = board_diff.compare(a, b)
        self.assertEqual(r["status"], "CHANGES_LISTED")
        self.assertEqual((r["copper"]["removed"], r["copper"]["added"]), (0, 1))
        self.assertEqual([f["reference"] for f in r["footprints"]], ["R1"])
        inside = board_diff.compare(a, b, regions=[(15, 5, 25, 15), (55, 35, 75, 45)])
        self.assertEqual(inside["status"], "CHANGES_INSIDE_REGIONS", inside["unexpected"])
        outside = board_diff.compare(a, b, regions=[(15, 5, 25, 15)])
        self.assertEqual(outside["status"], "UNEXPECTED_CHANGES")
        self.assertEqual({u["kind"] for u in outside["unexpected"]}, {"segment"})

    def test_removed_via_and_zone_change_are_reported(self):
        before = board_text()
        after = re.sub(r'\(via \(at [^)]*\)[^\n]*\n', "", board_text(zx=61))
        a, b = self.pair(before, after)
        r = board_diff.compare(a, b, regions=[(0, 0, 1, 1)])
        kinds = {u["kind"] for u in r["unexpected"]}
        self.assertIn("via", kinds)
        self.assertIn("zone", kinds)
        self.assertEqual(r["copper"]["by_kind_net"]["removed"], {"via A": 1})

    def test_short_import_piece_outside_regions_is_a_sliver(self):
        extra = '(segment (start 31 20) (end 31.05 20) (width 0.25) (layer "F.Cu") (net "A"))'
        a, b = self.pair(board_text(), board_text(extra=extra))
        r = board_diff.compare(a, b, regions=[(60, 40, 70, 45)])
        self.assertEqual(r["status"], "UNEXPECTED_CHANGES")
        self.assertEqual(len(r["slivers"]), 1)
        self.assertEqual(r["unexpected"], [])

    def test_cli_exit_code_and_evidence(self):
        from tools.cli.main import main
        extra = '(segment (start 70 50) (end 80 50) (width 0.25) (layer "B.Cu") (net "B"))'
        a, b = self.pair(board_text(), board_text(extra=extra))
        with redirect_stdout(io.StringIO()) as out:
            code = main(["board", "diff", str(a), str(b), "--region", "0", "0", "1", "1", "--project", str(self.tmp)])
        self.assertEqual(code, 20, out.getvalue())
        runs = list((self.tmp / "qa/generated/board-diff").glob("run-*/result.json"))
        self.assertEqual(json.loads(runs[0].read_text())["status"], "UNEXPECTED_CHANGES")


class FabCheckTests(TempDirTest):
    """Package files written to match the synthetic board, then broken one at a time."""

    def setUp(self):
        super().setUp()
        self.pcb = self.tmp / "board.kicad_pcb"
        self.pcb.write_text(board_text())
        self.pkg = self.tmp / "pkg"
        for sub in ("assembly", "fabrication/drill", "fabrication/gerbers"):
            (self.pkg / sub).mkdir(parents=True)
        self.positions = [{"Ref": "R1", "Val": "x", "Package": "R", "PosX": "30.000000", "PosY": "-20.000000",
                           "Rot": "90.000000", "Side": "top"}]
        self.write_positions()
        (self.pkg / "assembly/bom.csv").write_text('Refs,Value,Footprint,Qty,DNP,Manufacturer,MPN,Datasheet\n'
                                                   '"R1,R2",x,R,2,,Maker,P1,~\nJ1,x,J,1,,,,~\n')
        self.pth = {"T1C0.300": [(50.0, -20.0)], "T2C1.000": [(47.46, -40.0)]}
        self.write_drill("board-PTH.drl", "Plated,PTH", self.pth, ["ViaDrill", "ComponentDrill"])
        self.write_drill("board-NPTH.drl", "NonPlated,NPTH", {"T1C3.000": [(50.0, -37.0)]}, ["ComponentDrill"])
        (self.pkg / "fabrication/gerbers/board-job.gbrjob").write_text(json.dumps(
            {"GeneralSpecs": {"LayerNumber": 2, "BoardThickness": 1.6}, "MaterialStackup": []}))

    def write_positions(self):
        with (self.pkg / "assembly/positions.csv").open("w", newline="") as fp:
            w = csv.DictWriter(fp, fieldnames=list(self.positions[0]))
            w.writeheader()
            w.writerows(self.positions)

    def write_drill(self, name, function, tools, attrs):
        lines = ["M48", "; #@! TF.FileFunction,%s" % function, "FMAT,2", "METRIC",
                 "; #@! TF.FormatSpec,FORMAT={-:-/ absolute / metric / decimal}"]
        for (tool, _), attr in zip(tools.items(), attrs):
            lines += ["; #@! TA.AperFunction,%s,%s" % (function, attr), tool]
        lines.append("%")
        for tool, hits in tools.items():
            lines.append(tool.split("C")[0])
            lines += ["X%.3fY%.3f" % h for h in hits]
        lines.append("M30")
        (self.pkg / "fabrication/drill" / name).write_text("\n".join(lines) + "\n")

    def test_matching_package_passes(self):
        r = fab_check.check(self.pcb, self.pkg)
        self.assertEqual(r["status"], "PASS", r["errors"])
        self.assertTrue(r["drill"]["sets"]["PTH"]["equal"] and r["drill"]["sets"]["NPTH"]["equal"])
        self.assertIn("J1", r["warnings"][0])  # BOM line without MPN

    def test_position_rotation_side_and_dnp(self):
        self.positions[0].update(PosX="30.002000", Rot="0", Side="bottom")
        self.positions.append(dict(self.positions[0], Ref="R2"))
        self.write_positions()
        problems = {e["problem"].split(" ")[0] for e in fab_check.check(self.pcb, self.pkg)["errors"]}
        self.assertTrue({"position", "rotation", "side", "listed"} <= problems, problems)

    def test_drill_offset_at_file_resolution_and_missing_hole(self):
        self.pth["T2C1.000"] = [(47.461, -40.0)]          # 1 um: twice the tolerance of a 3-decimal file
        self.write_drill("board-PTH.drl", "Plated,PTH", self.pth, ["ViaDrill", "ComponentDrill"])
        r = fab_check.check(self.pcb, self.pkg)
        self.assertEqual(r["status"], "FAIL")
        self.assertEqual(r["errors"][0]["missing"][0]["owner"], "J1.1")
        self.assertAlmostEqual(r["drill"]["tolerance_mm"], 0.0005, places=6)

    def test_mixed_plating_file_and_limits(self):
        (self.pkg / "fabrication/drill/board.drl").write_text(
            "M48\n; #@! TF.FileFunction,MixedPlating,1,2\nMETRIC\n"
            "; #@! TF.FormatSpec,FORMAT={-:-/ absolute / metric / decimal}\n%\nM30\n")
        r = fab_check.check(self.pcb, self.pkg, limits={"min_via_drill_mm": 0.35, "min_component_hole_mm": 1.2})
        problems = " ".join(e["problem"] for e in r["errors"])
        self.assertIn("merged PTH/NPTH", problems)
        self.assertIn("via 0.300 mm below limit", problems)
        self.assertTrue(any("component hole 1.000" in w for w in r["warnings"]))
        self.assertEqual(fab_check.check(self.pcb, self.pkg)["limits"], {})

    def test_slots_are_reported_not_compared(self):
        self.pcb.write_text(board_text(extra="").replace('(drill 1.0)', '(drill oval 1.0 2.0)'))
        self.pth["T2C1.000"] = []
        self.write_drill("board-PTH.drl", "Plated,PTH", self.pth, ["ViaDrill", "ComponentDrill"])
        path = self.pkg / "fabrication/drill/board-PTH.drl"
        path.write_text(path.read_text().replace("M30", "T2\nX47.460Y-39.500G85X47.460Y-40.500\nM30"))
        r = fab_check.check(self.pcb, self.pkg)
        self.assertEqual(r["status"], "PASS", r["errors"])
        self.assertEqual(r["drill"]["slots"], {"board": 1, "files": 1, "compared": False})
        self.assertTrue(any(w.startswith("slots not compared") for w in r["warnings"]))

    def test_reference_ranges_match_the_exporter(self):
        from tools.release.exports import expand_refs
        for text in ("R1,R3-R5", "C10-C12, D1", "R7-R7", ""):
            self.assertEqual(fab_check.expand_refs(text), expand_refs(text))

    def test_layer_count_mismatch(self):
        (self.pkg / "fabrication/gerbers/board-job.gbrjob").write_text(json.dumps({"GeneralSpecs": {"LayerNumber": 4}}))
        self.assertIn("layer count", fab_check.check(self.pcb, self.pkg)["errors"][0]["problem"])


class NativeBoardReviewTests(TempDirTest):
    @requires_kicad
    def test_divider_export_matches_board_and_detects_a_moved_hole(self):
        from tools.release.exports import export_project
        root = self.fixture_copy()
        export_project(root, "T1", ibom=False)
        pkg = next((root / "manufacturing/releases/generated").glob("rev-T1-DRAFT*"))
        pcb = root / "divider.kicad_pcb"
        r = fab_check.check(pcb, pkg)
        self.assertEqual(r["status"], "PASS", r["errors"])
        drill = next((pkg / "fabrication/drill").glob("*-PTH.drl"))
        text = drill.read_text().splitlines()
        i = next(k for k, line in enumerate(text) if line.startswith("X"))
        x = text[i][1:].split("Y")[0]
        text[i] = text[i].replace("X" + x, "X%.3f" % (float(x) + 0.001), 1)
        drill.write_text("\n".join(text) + "\n")
        self.assertEqual(fab_check.check(pcb, pkg)["status"], "FAIL")
        self.assertEqual(board_diff.compare(pcb, pcb)["status"], "NO_CHANGES")
