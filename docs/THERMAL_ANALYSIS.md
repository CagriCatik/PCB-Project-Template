# Thermal analysis (phase 1)

`scripts/kit thermal analyze` estimates the steady-state temperature field of a
board from its real KiCad layout and the component power you provide. It
produces heatmaps, hotspots and per-component board temperatures.

**Everything it outputs is an estimate.** It does not replace thermocouple or
IR measurements on a prototype, and a PASS is not evidence of thermal safety.

## Usage

```sh
scripts/kit thermal analyze "<project>"                         # inputs from hardware/simulations/thermal/
scripts/kit thermal analyze "<project>" --power Q1=1.8 --power U2=0.6 --ambient 40 --grid 0.2
scripts/kit thermal compare <run_before> <run_after>            # e.g. before/after a copper or via change
```

Exit codes: 0 PASS, 20 FAIL (limit exceeded, unknown reference, energy balance),
19 missing inputs (no power sources) or missing numpy/scipy. Enable the gate in
`<project>/qa/verification.json` (`"thermal": "advisory"` or `"required"`) to run
it as part of `scripts/kit verify`; it is `disabled` by default because it needs
real power data.

## Inputs (per project, `hardware/simulations/thermal/`)

| File | Content |
| --- | --- |
| `power_sources.csv` | `reference, power_w, basis (calculation/datasheet/measurement/estimate), theta_jb_c_per_w, limit_c, notes`. Starts empty: KiCad does not know real losses. `--power REF=W` adds rows marked `estimate`. |
| `thermal.json` | `ambient_c`, `grid_mm`, `h_top_w_m2k`, `h_bottom_w_m2k`, `copper_k_w_mk`, `dielectric_k_inplane_w_mk`, `dielectric_k_through_w_mk`, `copper_thickness_mm` (null = from the board stack-up), `via_plating_mm`, `board_max_c`, `hotspot_count`, `hotspot_separation_mm`. Unknown keys are rejected. |

Defaults are typical literature values (h = 10 W/m²K still air incl. radiation,
copper 390 W/mK, FR-4 0.8 / 0.3 W/mK in-plane / through-plane, 25 µm via
plating, 105 °C board limit). The report lists every parameter with its source:
`default`, `thermal.json`, `override`, or the board stack-up.

From the board itself: Edge.Cuts outline (lines, arcs, rectangles, circles,
polygons, Béziers; holes/slots), board thickness, outer copper thickness from
the stack-up (0.035 mm if the board has none, reported), F.Cu/B.Cu tracks and
arcs, pads (rect/roundrect/circle/oval) with footprint rotation, saved zone
fills, vias and plated through holes, footprint side and courtyard.

## Model

Two nodes per grid cell (top and bottom copper side), finite-volume
discretization of `div(S grad T) − h (T − T_amb) + q = 0` per layer:

- sheet conductance per layer `S = k_cu · t_cu · copper_fraction + k_xy · t_board / 2`,
  copper fraction from 2×2 supersampled rasterization; harmonic mean between cells;
- vertical coupling `k_z · A / t_board` plus `k_cu · π · d · t_plating / t_board` per via/plated hole;
- convection `h · A` on both faces to ambient;
- a component's power enters through its pads on its own side (courtyard box if
  it has none), weighted by pad area;
- sparse direct solve (SciPy); results are rejected unless the energy balance
  closes (power out = power in to 1e-6 relative).

Component values: `board_max_c` / `board_mean_c` are board temperatures under
the part. With `theta_jb_c_per_w` the report adds
`junction_estimate_c = board_max_c + P · θJB`; limits use that value if present.

## Outputs (`<project>/qa/generated/thermal/<run>/`, ignored by Git)

`temperature_top.png`, `temperature_bottom.png` (viewed from the top, bottom not
mirrored; white boxes = component extents, cyan crosses = top hotspots),
`colorbar.png`, `thermal_report.html` (self-contained), `component_temperatures.csv`,
`hotspots.csv`, `temperature_field.npz` (x, y, mask, top/bottom °C) and
`thermal.json` (all inputs, results, findings, warnings).

## Validation

Automated (`qa/tests/test_thermal.py`):

| Case | Reference | Result |
| --- | --- | --- |
| Uniform heating, two-node network | closed form | matches to 1e-9 relative |
| 1D copper fin, insulated end | `θ(x) = q'/√(hS) · cosh(m(L−x))/sinh(mL)` | within 1 % at 4 positions |
| Point source on a square plate | symmetry, energy balance | symmetric to 1e-10, balance to 1e-10 W |
| Slot splitting the board | isolated island stays at ambient | exact |
| Fixture grid refinement | 0.5 / 0.25 / 0.125 mm | 80.8 / 83.9 / 84.4 °C (0.25 mm within 1 % of 0.125 mm) |
| Pad placement on rotated footprints | KiCad pcbnew 10.0.7 positions | identical (< 1e-6 mm) |

Not validated: absolute temperatures of any real board. That needs measurement.

## Limitations (phase 1)

- Inner copper layers are not modelled (reported; spreading underestimated, so
  temperatures tend to be overestimated on multilayer boards).
- No trace/via Joule heating (I²R); add it as component power until phase 2.
- Steady state only; no transient, no 3D component bodies, heatsinks or
  enclosure; edge convection and airflow only via `h_top` / `h_bottom`.
- Unfilled zones contribute no copper (reported): fill zones and save first.
- Roundrect/custom pads use their bounding rectangle.

## Roadmap

Phase 2: inner layers, anisotropic stack-up, I²R heating from net currents,
optional FiPy/SfePy cross-checks. Phase 3: transient and 3D fields (VTK export,
PyVista). Each phase needs its own analytic and measured benchmarks before use.
