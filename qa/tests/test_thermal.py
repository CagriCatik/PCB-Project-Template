"""Thermal estimate: analytic benchmarks for the solver, geometry, outputs and integration."""

import csv
import json
import math
import unittest

from kit_test_support import TempDirTest, requires_kicad

try:
    import numpy as np
    import scipy  # noqa: F401
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

needs_numpy = unittest.skipUnless(HAVE_NUMPY, "numpy/scipy not installed in this interpreter (use .venv)")

if HAVE_NUMPY:
    from tools.thermal.solver import solve

K_CU, T_CU, H = 390.0, 35e-6, 10.0


def uniform(shape, value):
    return np.full(shape, float(value))


@needs_numpy
class AnalyticBenchmarks(unittest.TestCase):
    """Cases with closed-form solutions; the discretization must reproduce them."""

    def test_uniform_heating_two_node_exact(self):
        # Uniform power only into the top layer: no lateral flow, two-node network
        #   θb = Gv p / (hA (hA + 2Gv)),  θt = p (hA + Gv) / (hA (hA + 2Gv)).
        shape, cell, p, gv = (12, 17), 1e-3, 2e-4, 3e-4
        hA = H * cell * cell
        r = solve(np.ones(shape, bool), uniform(shape, 0.01), uniform(shape, 0.01), uniform(shape, gv),
                  H, H, uniform(shape, p), uniform(shape, 0), cell, 25.0)
        tb = gv * p / (hA * (hA + 2 * gv))
        tt = p * (hA + gv) / (hA * (hA + 2 * gv))
        np.testing.assert_allclose(r["top"], 25 + tt, rtol=1e-9)
        np.testing.assert_allclose(r["bottom"], 25 + tb, rtol=1e-9)
        self.assertAlmostEqual(r["power_out_w"], r["power_in_w"], places=12)

    def test_one_dimensional_fin(self):
        # Strip of copper sheet, heat Q per layer entering at x=0, convection h, insulated far end:
        #   θ(x) = q'/(sqrt(h S)) * cosh(m (L-x)) / sinh(m L),  m = sqrt(h/S),  S = k t.
        cell, nx, ny = 0.05e-3, 800, 3
        S = K_CU * T_CU
        sheet = uniform((ny, nx), S)
        power = np.zeros((ny, nx))
        q_layer = 0.05
        power[:, 0] = q_layer / ny
        r = solve(np.ones((ny, nx), bool), sheet, sheet, uniform((ny, nx), 0.0), H, H, power, power, cell, 0.0)
        m, L, qp = math.sqrt(H / S), nx * cell, q_layer / (ny * cell)
        for x_cells in (0, 200, 400, 799):
            x = (x_cells + 0.5) * cell
            exact = qp / math.sqrt(H * S) * math.cosh(m * (L - x)) / math.sinh(m * L)
            self.assertAlmostEqual(r["top"][1, x_cells] / exact, 1.0, delta=0.01, msg="x=%.2f mm" % (x * 1e3))
        np.testing.assert_allclose(r["top"], r["bottom"], rtol=1e-12)

    def test_point_source_symmetry_and_balance(self):
        n, cell = 41, 0.5e-3
        power = np.zeros((n, n))
        power[n // 2, n // 2] = 0.5
        sheet = uniform((n, n), K_CU * T_CU)
        r = solve(np.ones((n, n), bool), sheet, sheet * 0.3, uniform((n, n), 1e-3), H, 2 * H, power,
                  np.zeros((n, n)), cell, 20.0)
        for field in (r["top"], r["bottom"]):
            np.testing.assert_allclose(field, field[::-1, :], rtol=1e-10)
            np.testing.assert_allclose(field, field.T, rtol=1e-10)
        self.assertAlmostEqual(r["power_out_w"], 0.5, places=10)
        self.assertGreater(r["top"].max(), r["bottom"].max())
        self.assertEqual(np.unravel_index(np.nanargmax(r["top"]), r["top"].shape), (n // 2, n // 2))

    def test_cells_outside_outline_carry_no_heat(self):
        mask = np.ones((10, 10), bool)
        mask[:, 5] = False  # a slot splits the board into two islands
        power = np.zeros((10, 10))
        power[5, 2] = 0.1
        r = solve(mask, uniform((10, 10), 0.01), uniform((10, 10), 0.01), uniform((10, 10), 1e-3), H, H,
                  power, np.zeros((10, 10)), 1e-3, 25.0)
        self.assertTrue(np.isnan(r["top"][:, 5]).all())
        np.testing.assert_allclose(r["top"][:, 6:], 25.0, atol=1e-12)  # isolated island stays at ambient


@needs_numpy
class FixtureModelTests(TempDirTest):
    def board(self, power=("R1=0.125", "R2=0.125"), **kw):
        from tools.thermal.analysis import analyze

        self._copies = getattr(self, "_copies", 0) + 1
        project = self.fixture_copy("fixture %d" % self._copies)
        return project, analyze(project, extra_power=list(power), **kw)

    def test_geometry_of_fixture(self):
        from tools.thermal.geometry import load_board, rasterize

        board = load_board(self.fixture_copy() / "divider.kicad_pcb")
        self.assertEqual(board["thickness_mm"], 1.6)
        self.assertIn("default", board["copper_source"])
        grid, mask, copper = rasterize(board, 0.25)
        self.assertAlmostEqual(mask.sum() * 0.0625, 23 * 17, delta=1.0)
        self.assertGreater(copper["F.Cu"].sum(), 0)
        self.assertGreater(copper["B.Cu"].sum(), 0)  # THT header pads exist on both sides
        self.assertTrue(set(board["footprints"]) == {"J1", "R1", "R2"})

    def test_analysis_outputs_and_energy_balance(self):
        project, r = self.board()
        from pathlib import Path

        out = Path(r["output_directory"])
        self.assertEqual(r["status"], "PASS", r["findings"])
        self.assertTrue(r["estimate"])
        self.assertAlmostEqual(r["summary"]["power_out_w"], 0.25, places=9)
        mean_rise = 0.25 / (2 * H * r["summary"]["board_area_mm2"] * 1e-6)
        self.assertGreater(r["summary"]["max_top_c"] - 25, mean_rise)  # local hotspot above the average rise
        for name in ("temperature_top.png", "temperature_bottom.png", "colorbar.png"):
            data = (out / name).read_bytes()
            self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", name)
        html = (out / "thermal_report.html").read_text()
        self.assertIn("ESTIMATE", html)
        self.assertIn("data:image/png;base64,", html)
        rows = list(csv.DictReader((out / "component_temperatures.csv").open()))
        self.assertEqual({r["reference"] for r in rows}, {"R1", "R2"})
        self.assertEqual(rows[0]["heat_entry"], "pads")
        self.assertTrue(list(csv.DictReader((out / "hotspots.csv").open())))
        self.assertEqual(json.loads((out / "thermal.json").read_text())["status"], "PASS")
        field = np.load(out / "temperature_field.npz")
        self.assertEqual(field["top_c"].shape, field["mask"].shape)
        self.assertEqual(r["hotspots"][0]["nearest"] in ("R1", "R2"), True)

    def test_grid_refinement_converges(self):
        _, coarse = self.board(grid_mm=0.5)
        _, fine = self.board(grid_mm=0.2)
        rise_c, rise_f = coarse["summary"]["max_top_c"] - 25, fine["summary"]["max_top_c"] - 25
        self.assertLess(abs(rise_c - rise_f) / rise_f, 0.15)

    def test_more_copper_or_convection_lowers_temperature(self):
        _, base = self.board()
        _, repeat = self.board(power=("R1=0.125", "R2=0.125"))  # determinism
        project = self.fixture_copy("hotter h")
        (project / "hardware/simulations/thermal").mkdir(parents=True)
        (project / "hardware/simulations/thermal/thermal.json").write_text(json.dumps({"h_top_w_m2k": 30.0}))
        from tools.thermal.analysis import analyze

        better = analyze(project, extra_power=["R1=0.125", "R2=0.125"])
        self.assertLess(better["summary"]["max_top_c"], base["summary"]["max_top_c"])
        self.assertEqual(better["assumptions"]["h_top_w_m2k"]["source"], "thermal.json")
        self.assertAlmostEqual(base["summary"]["max_top_c"], repeat["summary"]["max_top_c"], places=9)

    def test_limits_and_junction_estimate(self):
        project = self.fixture_copy()
        folder = project / "hardware/simulations/thermal"
        folder.mkdir(parents=True)
        (folder / "power_sources.csv").write_text(
            "reference,power_w,basis,theta_jb_c_per_w,limit_c,notes\n"
            "R1,0.25,calculation,40,70,test-only values\n")
        from tools.thermal.analysis import analyze

        r = analyze(project)
        comp = r["components"][0]
        self.assertAlmostEqual(comp["junction_estimate_c"], comp["board_max_c"] + 10.0, places=6)
        self.assertEqual(comp["status"], "FAIL")
        self.assertEqual(r["status"], "FAIL")
        (folder / "thermal.json").write_text(json.dumps({"board_max_c": 30.0}))
        self.assertTrue(any("board_max_c" in f for f in analyze(project)["findings"]))

    def test_input_errors(self):
        from tools.core.common import KitError
        from tools.thermal.analysis import analyze

        project = self.fixture_copy()
        with self.assertRaises(KitError) as ctx:
            analyze(project)  # no power sources at all
        self.assertEqual(ctx.exception.exit_code, 19)
        folder = project / "hardware/simulations/thermal"
        folder.mkdir(parents=True)
        for content in ("reference,power_w,basis\nR1,-1,estimate\n", "reference,power_w,basis\nR1,x,estimate\n",
                        "reference,power_w,basis\nR1,1,guess\n"):
            (folder / "power_sources.csv").write_text(content)
            with self.subTest(content=content), self.assertRaises(KitError):
                analyze(project)
        (folder / "power_sources.csv").write_text("reference,power_w,basis\nR1,0.1,datasheet\n")
        (folder / "thermal.json").write_text(json.dumps({"h_top": 5}))
        with self.assertRaises(KitError):
            analyze(project)
        (folder / "thermal.json").write_text(json.dumps({"grid_mm": 0}))
        with self.assertRaises(KitError):
            analyze(project)

    def test_unknown_reference_is_a_finding(self):
        _, r = self.board(power=("R1=0.1", "U99=1.0"))
        self.assertEqual(r["status"], "FAIL")
        self.assertTrue(any("U99" in f for f in r["findings"]))

    def test_sources_untouched_and_lock_respected(self):
        from tools.core.common import KitError, source_hashes
        from tools.thermal.analysis import analyze

        project = self.fixture_copy()
        before = source_hashes(project)
        analyze(project, extra_power=["R1=0.1"])
        self.assertEqual(before, source_hashes(project))
        (project / "~divider.kicad_pcb.lck").write_text("{}")
        with self.assertRaises(KitError):
            analyze(project, extra_power=["R1=0.1"])

    def test_compare_runs(self):
        from tools.thermal.compare import compare

        project, a = self.board(power=("R1=0.125", "R2=0.125"))
        b = __import__("tools.thermal.analysis", fromlist=["analyze"]).analyze(project, extra_power=["R1=0.25",
                                                                                                    "R2=0.125"])
        result = compare(a["output_directory"], b["output_directory"])
        self.assertFalse(result["comparable"])  # total power differs
        r1 = next(c for c in result["components"] if c["reference"] == "R1")
        self.assertGreater(r1["delta_k"], 0)

    def test_cli_and_gate(self):
        from tools.cli.main import main
        from tools.quality.verification import verify

        project = self.fixture_copy()
        self.assertEqual(main(["thermal", "analyze", str(project), "--power", "R1=0.1", "--grid", "0.5"]), 0)
        self.assertEqual(main(["thermal", "analyze", str(project)]), 19)
        (project / "hardware/simulations/thermal").mkdir(parents=True)
        (project / "hardware/simulations/thermal/power_sources.csv").write_text(
            "reference,power_w,basis\nR2,0.1,datasheet\n")
        (project / "qa").mkdir(exist_ok=True)
        (project / "qa/verification.json").write_text(json.dumps({"gates": {"thermal": "required"}}))
        result = verify(project, gates=["thermal"])
        self.assertEqual(result["gates"]["thermal"]["status"], "PASS", result["gates"]["thermal"])
        self.assertTrue(result["gates"]["thermal"]["estimate"])


@needs_numpy
@requires_kicad
class KiCadCrossCheckTests(TempDirTest):
    def test_pad_positions_match_pcbnew_on_rotated_footprints(self):
        from tools.core import kicad_env
        from tools.core.common import run
        from tools.project.templates import create
        from tools.thermal.geometry import load_board

        project, _ = create("arduino-shield", self.tmp / "uno thermal", "uno thermal", register=False)
        pcb = project / "uno thermal.kicad_pcb"
        script = ("import pcbnew,sys,json;b=pcbnew.LoadBoard(sys.argv[1]);print(json.dumps([[f.GetReference(),"
                  "pcbnew.ToMM(p.GetPosition().x),pcbnew.ToMM(p.GetPosition().y)] for f in b.GetFootprints() "
                  "for p in f.Pads()]))")
        record = run([kicad_env.bundled_python(), "-c", script, pcb])
        reference = json.loads(record["stdout"].strip().splitlines()[-1])
        board = load_board(pcb)
        mine = [(ref, p["x"], p["y"]) for ref, fp in board["footprints"].items() for p in fp["pads"]]
        self.assertEqual(len(mine), len(reference))
        for ref, x, y in reference:
            err = min(abs(x - a) + abs(y - b) for r, a, b in mine if r == ref)
            self.assertLess(err, 1e-6, ref)
        self.assertEqual(len(board["outline"]), 1)  # lines + arcs chained into one loop
        from tools.thermal.analysis import analyze

        r = analyze(project, extra_power=["J1=0.2"], grid_mm=0.5)
        self.assertAlmostEqual(r["summary"]["power_out_w"], 0.2, places=8)


if __name__ == "__main__":
    unittest.main()
