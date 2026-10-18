"""Thermal analysis orchestration: inputs -> geometry -> solve -> reports -> verdict.

Reads only; the project's design files are hashed before and after. Outputs go
to <project>/qa/generated/thermal/<timestamp>-<id>/ unless --output is given.
"""

import csv
import math
from pathlib import Path
import tempfile

from tools.core.common import KitError, check_locks, now, project_files, source_hashes, write_json
from tools.thermal import config as cfg
from tools.thermal.geometry import OUTER, _np, footprint_weights, load_board, rasterize
from tools.thermal.render import colorbar, heatmap, report
from tools.thermal.solver import solve


def build_model(board, config):
    """Grid, mask, coverage and per-cell conductances for one board."""
    np = _np()
    grid, mask, copper = rasterize(board, config["grid_mm"])
    t_board = board["thickness_mm"] * 1e-3
    t_cu = {l: (config["copper_thickness_mm"].get(l) or board["copper_mm"][l]) * 1e-3 for l in OUTER}
    k_cu, k_xy, k_z = (config[k] for k in ("copper_k_w_mk", "dielectric_k_inplane_w_mk", "dielectric_k_through_w_mk"))
    sheet = {l: (k_cu * t_cu[l] * copper[l] + k_xy * t_board / 2) * mask for l in OUTER}
    cell_m = config["grid_mm"] * 1e-3
    vertical = np.full(mask.shape, k_z * cell_m * cell_m / t_board) * mask
    barrels = [(v["x"], v["y"], v["drill"]) for v in board["vias"]]
    barrels += [(p["x"], p["y"], p["drill"]) for fp in board["footprints"].values() for p in fp["pads"]
                if p["plated"] and p["drill"] > 0 and set(OUTER) <= p["layers"]]
    plating = config["via_plating_mm"] * 1e-3
    for x, y, drill in barrels:
        cell = grid.cell_of(x, y)
        if cell and mask[cell]:
            vertical[cell] += k_cu * math.pi * drill * 1e-3 * plating / t_board
    return {"grid": grid, "mask": mask, "copper": copper, "sheet": sheet, "vertical": vertical,
            "cell_m": cell_m, "barrels": len(barrels), "t_cu_mm": {l: t_cu[l] * 1e3 for l in OUTER}}


def _hotspots(fields, mask, grid, footprints, count, separation):
    np = _np()
    picked = []
    candidates = []
    for layer, field in fields.items():
        vals = np.where(mask, field, -np.inf)
        order = np.argsort(vals, axis=None)[::-1][: max(2000, count * 50)]
        candidates += [(float(vals.flat[k]), layer, *np.unravel_index(k, vals.shape)) for k in order]
    for temp, layer, i, j in sorted(candidates, reverse=True):
        x, y = float(grid.xc[j]), float(grid.yc[i])
        if any(p["layer"] == layer and math.hypot(p["x_mm"] - x, p["y_mm"] - y) < separation for p in picked):
            continue
        near = min(footprints.values(), key=lambda f: math.hypot(f["x"] - x, f["y"] - y), default=None)
        picked.append({"rank": len(picked) + 1, "layer": layer, "x_mm": round(x, 3), "y_mm": round(y, 3),
                       "temperature_c": round(temp, 2), "nearest": near["reference"] if near else ""})
        if len(picked) >= count:
            break
    return picked


def analyze(project, output=None, ambient=None, grid_mm=None, extra_power=None, require_power=True):
    np = _np()
    project = Path(project).resolve()
    files = project_files(project)
    check_locks(project)
    before = source_hashes(project)
    config, sources, config_file = cfg.load_config(project, {"ambient_c": ambient, "grid_mm": grid_mm})
    power_rows, power_file = cfg.load_power(project, extra_power)
    findings, warnings = [], []
    if require_power and not any(r["power_w"] > 0 for r in power_rows):
        raise KitError("No power sources: list component dissipation in %s/power_sources.csv (or use --power "
                       "REF=W). KiCad does not know real losses." % cfg.FOLDER, 19)
    board = load_board(files[2])
    warnings += board["warnings"]
    model = build_model(board, config)
    grid, mask = model["grid"], model["mask"]
    power = {l: np.zeros(mask.shape) for l in OUTER}
    components = []
    for row in power_rows:
        fp = board["footprints"].get(row["reference"])
        entry = dict(row)
        if fp is None:
            findings.append("Power source %s is not a footprint on the board." % row["reference"])
            entry.update(side="?", heat_entry="missing", status="ERROR")
            components.append(entry)
            continue
        weights, basis = footprint_weights(grid, fp, mask)
        if weights is None:
            findings.append("%s has no pads or courtyard inside the outline; its power was not applied." % fp["reference"])
            entry.update(side=fp["side"], heat_entry="none", status="ERROR")
            components.append(entry)
            continue
        power[fp["side"]] += row["power_w"] * weights
        entry.update(side=fp["side"], heat_entry=basis, _weights=weights)
        components.append(entry)
    result = solve(mask, model["sheet"]["F.Cu"], model["sheet"]["B.Cu"], model["vertical"],
                   config["h_top_w_m2k"], config["h_bottom_w_m2k"], power["F.Cu"], power["B.Cu"],
                   model["cell_m"], config["ambient_c"])
    fields = {"F.Cu": result["top"], "B.Cu": result["bottom"]}
    limit = float(config["board_max_c"])
    for entry in components:
        weights = entry.pop("_weights", None)
        if weights is None:
            continue
        field = fields[entry["side"]]
        under = weights > 0
        entry["board_max_c"] = round(float(np.nanmax(field[under])), 2)
        entry["board_mean_c"] = round(float((field[under] * weights[under]).sum()), 2)
        if entry["theta_jb_c_per_w"] is not None:
            entry["junction_estimate_c"] = round(entry["board_max_c"] + entry["power_w"] * entry["theta_jb_c_per_w"], 2)
        check = entry.get("junction_estimate_c", entry["board_max_c"])
        entry["status"] = "PASS"
        if entry["limit_c"] is not None and check > entry["limit_c"]:
            entry["status"] = "FAIL"
            findings.append("%s estimate %.1f °C exceeds its limit %.1f °C." % (entry["reference"], check,
                                                                                entry["limit_c"]))
    t_max = {l: float(np.nanmax(f)) for l, f in fields.items()}
    for layer, value in t_max.items():
        if value > limit:
            findings.append("%s side reaches %.1f °C, above board_max_c %.1f °C." % (layer, value, limit))
    balance = abs(result["power_in_w"] - result["power_out_w"]) <= 1e-6 * max(result["power_in_w"], 1e-9) + 1e-9
    if not balance:
        findings.append("Energy balance not satisfied; solver result rejected.")
    hotspots = _hotspots(fields, mask, grid, board["footprints"], int(config["hotspot_count"]),
                         float(config["hotspot_separation_mm"]))
    if source_hashes(project) != before:
        findings.append("Design sources changed during analysis.")
    warnings += [
        "Trace and via Joule heating (I²R) is not modelled (phase 2); add it as component power if significant.",
        "Edge convection, radiation to nearby parts, enclosures and airflow are only represented by h_top/h_bottom.",
        "Pads with roundrect/custom shapes are approximated by their bounding rectangle.",
    ]
    if any(r["basis"] == "estimate" for r in power_rows):
        warnings.append("Some power values are marked 'estimate'; replace them with calculations or measurements.")

    out = Path(output) if output else project / "qa/generated/thermal"
    out.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix=now().replace(":", "")[:15] + "-", dir=out)) if not output else out
    t_lo = float(config["ambient_c"])
    t_hi = max(max(t_max.values()), t_lo + 0.1)
    for layer, name in (("F.Cu", "temperature_top.png"), ("B.Cu", "temperature_bottom.png")):
        side_fps = [f for f in board["footprints"].values() if f["side"] == layer]
        heatmap(out / name, fields[layer], mask, t_lo, t_hi, grid, side_fps,
                [h for h in hotspots if h["layer"] == layer][:5])
    colorbar(out / "colorbar.png")
    np.savez_compressed(out / "temperature_field.npz", x_mm=grid.xc, y_mm=grid.yc, mask=mask,
                        top_c=fields["F.Cu"], bottom_c=fields["B.Cu"])
    columns = ["reference", "side", "power_w", "basis", "heat_entry", "board_max_c", "board_mean_c",
               "theta_jb_c_per_w", "junction_estimate_c", "limit_c", "status", "notes"]
    _csv(out / "component_temperatures.csv", components, columns)
    _csv(out / "hotspots.csv", hotspots, ["rank", "layer", "x_mm", "y_mm", "temperature_c", "nearest"])
    assumptions = {k: {"value": config[k], "source": sources.get(k, "default"), "note": cfg.NOTES.get(k, "")}
                   for k in cfg.DEFAULTS if k != "schema"}
    assumptions["board_thickness_mm"] = {"value": board["thickness_mm"], "source": "board (general)"}
    assumptions["copper_thickness_mm"] = {"value": model["t_cu_mm"], "source": board["copper_source"]
                                          if not any(config["copper_thickness_mm"].values()) else "thermal.json"}
    summary = {"ambient_c": config["ambient_c"], "grid_mm": config["grid_mm"], "unknowns": result["unknowns"],
               "power_in_w": result["power_in_w"], "power_out_w": result["power_out_w"],
               "residual_w": result["residual_w"], "max_top_c": t_max["F.Cu"], "max_bottom_c": t_max["B.Cu"],
               "board_max_c": limit, "scale_min_c": t_lo, "scale_max_c": t_hi, "plated_barrels": model["barrels"],
               "copper_area_top_mm2": float(model["copper"]["F.Cu"].sum() * config["grid_mm"] ** 2),
               "board_area_mm2": float(mask.sum() * config["grid_mm"] ** 2)}
    data = {"schema": 1, "at": now(), "project": files[0].stem, "board": str(files[2]),
            "status": "PASS" if not findings else "FAIL", "estimate": True, "summary": summary,
            "components": components, "hotspots": hotspots, "findings": findings, "warnings": warnings,
            "assumptions": assumptions, "inputs": {"thermal_json": config_file, "power_sources_csv": power_file},
            "output_directory": str(out),
            "disclaimer": "Estimate from a simplified steady-state model; validate by measurement."}
    report(out / "thermal_report.html", data, out)
    write_json(out / "thermal.json", data)
    return data


def _csv(path, rows, columns):
    with path.open("w", newline="") as fp:
        writer = csv.DictWriter(fp, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k) for k in columns})


def summary_lines(result):
    s = result["summary"]
    lines = ["Thermal estimate: %s  (ESTIMATE, not a measurement)" % result["status"],
             "  power %.3f W, ambient %.1f °C, grid %s mm" % (s["power_in_w"], s["ambient_c"], s["grid_mm"]),
             "  max top %.1f °C, max bottom %.1f °C (limit %.1f °C)" % (s["max_top_c"], s["max_bottom_c"],
                                                                        s["board_max_c"])]
    for c in result["components"]:
        lines.append("  %-8s %6.3f W  board max %s °C  %s" % (c["reference"], c["power_w"], c.get("board_max_c", "-"),
                                                               c.get("status")))
    lines += ["  ! " + f for f in result["findings"]]
    lines.append("Report: %s/thermal_report.html" % result["output_directory"])
    return lines
