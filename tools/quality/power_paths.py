"""DC current distribution in the actual copper of one net. ESTIMATE, not a measurement.

Cases: hardware/simulations/power/current-paths.json (schema 1)
  {"schema": 1, "plating": "<assumption id, mm>", "cases": [
     {"id": "vbat_in", "net": "/Power/VBAT_IN", "layers": ["F.Cu", "B.Cu"],
      "source": [["J101", "2"]],
      "sinks": [{"label": "F101 input", "pads": [["F101", "1"]], "current": "<assumption id, A>",
                 "direction": "out"}]}]}
Every current and the hole-wall plating thickness reference hardware/interfaces/assumptions.json; no
values are built in. direction "out" draws the current out of the net at the sink (default), "in" feeds
it in (return currents on ground).

Model: KiCad's own Python (pcbnew) turns the net's filled zones, tracks, via rings and pads into
polygons per layer; they are rasterised on a square grid. Neighbouring copper cells are joined by the
sheet conductance of the layer's copper thickness from the board stack-up; vias and plated pad holes join
the layers with the barrel resistance (stated plating, distance between layer centres); every terminal pad
is equipotential. The source is held at 0 V, each sink draws its current, the linear network is solved
directly (scipy). Not modelled: temperature rise, plating tolerance, solder-filled holes, AC effects,
connector contact resistance. Copper outside the region (if given) is ignored.
"""
import json
import math
from pathlib import Path
import re
import struct
import zlib

from tools.core import kicad_env
from tools.core.common import KitError, now, project_files, run, sha256, write_json
from tools.project.assumptions import Assumptions

RHO = 1.72e-8      # ohm m, copper at 20 degC (handbook value)
G_TERM = 1e4       # S per cell, equipotential pad tie
STEPS = [(0.5, (40, 60, 120)), (1.0, (40, 120, 220)), (2.0, (60, 180, 80)), (3.0, (230, 210, 40)),
         (5.0, (240, 130, 30)), (1e9, (220, 30, 30))]

EXTRACT = r'''
import json, os, sys
import pcbnew
cfg = json.loads(open(sys.argv[1]).read())
T, M = pcbnew.ToMM, pcbnew.FromMM
b = pcbnew.LoadBoard(cfg["board"])
net = b.FindNet(cfg["net"])
if net is None:
    json.dump({"error": "net %s not on the board" % cfg["net"]}, open(cfg["output"], "w")); os._exit(0)
nc = net.GetNetCode()
lids = {}
for ln in cfg["layers"]:
    lid = b.GetLayerID(ln)
    if lid < 0:
        json.dump({"error": "layer %s not on the board" % ln}, open(cfg["output"], "w")); os._exit(0)
    lids[ln] = lid

def contours(ps):
    out = []
    for i in range(ps.OutlineCount()):
        for h in range(-1, ps.HoleCount(i)):
            c = ps.Outline(i) if h < 0 else ps.Hole(i, h)
            out.append([(round(T(c.CPoint(k).x), 5), round(T(c.CPoint(k).y), 5)) for k in range(c.PointCount())])
    return out

def shape(item, L):
    ps = pcbnew.SHAPE_POLY_SET()
    item.TransformShapeToPolygon(ps, L, 0, M(0.005), pcbnew.ERROR_INSIDE)
    return contours(ps)

e = b.GetBoardEdgesBoundingBox()
out = {"layers": {}, "pads": [], "vias": [], "extent": None,
       "outline_bbox": None}
xs = []
for ln, L in lids.items():
    lay = {"zones": [], "items": []}
    for z in b.Zones():
        if z.GetNetCode() == nc and z.IsOnLayer(L) and not z.GetIsRuleArea():
            lay["zones"].append(contours(z.GetFilledPolysList(L)))
    for t in b.GetTracks():
        if t.GetNetCode() != nc:
            continue
        if (t.GetClass() == "PCB_VIA" and t.IsOnLayer(L)) or (t.GetClass() != "PCB_VIA" and t.GetLayer() == L):
            lay["items"].append(shape(t, L))
    out["layers"][ln] = lay
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetNetCode() != nc:
            continue
        rec = {"ref": f.GetReference(), "number": p.GetNumber(), "x": T(p.GetPosition().x), "y": T(p.GetPosition().y),
               "drill": T(p.GetDrillSize().x) if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else 0.0, "shapes": {}}
        for ln, L in lids.items():
            if p.IsOnLayer(L):
                rec["shapes"][ln] = shape(p, L)
        out["pads"].append(rec)
for t in b.GetTracks():
    if t.GetNetCode() == nc and t.GetClass() == "PCB_VIA":
        out["vias"].append({"x": T(t.GetPosition().x), "y": T(t.GetPosition().y), "drill": T(t.GetDrill())})
boxes = [it.GetBoundingBox() for it in [p for f in b.GetFootprints() for p in f.Pads() if p.GetNetCode() == nc]
         + [t for t in b.GetTracks() if t.GetNetCode() == nc] + [z for z in b.Zones() if z.GetNetCode() == nc]]
if boxes:
    out["extent"] = [min(T(r.GetLeft()) for r in boxes), min(T(r.GetTop()) for r in boxes),
                     max(T(r.GetRight()) for r in boxes), max(T(r.GetBottom()) for r in boxes)]
json.dump(out, open(cfg["output"], "w"))
os._exit(0)
'''


def _np():
    try:
        import numpy
        import scipy.sparse  # noqa: F401
    except ImportError:
        raise KitError("Power paths need numpy and scipy (.venv from requirements.txt).", 19)
    return numpy


def stackup(board_text):
    """Copper thickness (m) and centre depth (mm from the top) of each copper layer from (stackup ...)."""
    if "(stackup" not in board_text:
        raise KitError("Board has no stack-up; define it in Board Setup so copper thickness is stated.", 13)
    blk = board_text[board_text.index("(stackup"):]
    blk = blk[:blk.index("(copper_finish")] if "(copper_finish" in blk else blk[:20000]
    tcu, z, pos = {}, {}, 0.0
    for m in re.finditer(r'\(layer "([^"]+)"\s*\(type "([^"]+)"\)(.*?)(?=\(layer "|\Z)', blk, re.S):
        name, typ, body = m.groups()
        th = re.search(r"\(thickness ([0-9.]+)", body)
        th = float(th.group(1)) if th else 0.0
        if typ == "copper":
            tcu[name], z[name] = th * 1e-3, pos + th / 2
        if typ == "copper" or name.startswith("dielectric"):
            pos += th
    return tcu, z


def raster(np, conts, x0, y0, nx, ny, g):
    """Even-odd scanline fill of polygon contours at the cell centres."""
    m = np.zeros((ny, nx), bool)
    conts = [np.asarray(c, float) for c in conts if len(c) >= 3]
    if not conts:
        return m
    a = np.concatenate(conts)
    b = np.concatenate([np.roll(c, -1, axis=0) for c in conts])
    ys = y0 + (np.arange(ny) + 0.5) * g
    xs = x0 + (np.arange(nx) + 0.5) * g
    for j, y in enumerate(ys):
        s = (a[:, 1] <= y) != (b[:, 1] <= y)
        if not s.any():
            continue
        xa, ya, xb, yb = a[s, 0], a[s, 1], b[s, 0], b[s, 1]
        xi = np.sort(xa + (y - ya) * (xb - xa) / (yb - ya))
        for k in range(0, len(xi) - 1, 2):
            m[j, (xs >= xi[k]) & (xs < xi[k + 1])] = True
    return m


def png(path, rgb):
    h, w, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[r].astype("uint8").tobytes() for r in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                           + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def load_cases(project):
    path = Path(project).resolve() / "hardware/simulations/power/current-paths.json"
    if not path.is_file():
        raise KitError("No current-path cases: create %s (see docs/engineering/power-paths.md)" % path, 13)
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("schema") != 1 or not isinstance(data.get("cases"), list):
        raise KitError("current-paths.json needs schema 1 with a cases array", 13)
    return path, data


def extract(board, net, layers, folder):
    python = kicad_env.bundled_python()
    if not python:
        raise KitError("Power paths need KiCad %s (bundled Python with pcbnew)." % kicad_env.KICAD_VERSION, 3)
    cfg, geo = folder / "extract.json", folder / "geometry.json"
    write_json(cfg, {"board": str(board), "net": net, "layers": layers, "output": str(geo)})
    script = folder / "extract.py"
    script.write_text(EXTRACT)
    rec = run([python, script, cfg], timeout=600)
    if not geo.is_file():
        raise KitError("Geometry extraction failed: %s" % rec["stderr"][-400:], 13)
    data = json.loads(geo.read_text())
    if "error" in data:
        raise KitError(data["error"], 13)
    script.unlink()
    return data


def solve(geo, case, currents, plating_mm, tcu, zc, grid, region, origin, folder):
    np = _np()
    import scipy.sparse as sp
    import scipy.sparse.linalg as spl
    from scipy.sparse.csgraph import connected_components

    layers = case["layers"]
    for ln in layers:
        if ln not in tcu or tcu[ln] <= 0:
            raise KitError("Stack-up gives no copper thickness for %s" % ln, 13)
    if not geo["extent"]:
        raise KitError("Net %s has no copper" % case["net"], 13)
    x0, y0, x1, y1 = geo["extent"]
    x0, y0, x1, y1 = x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5
    if region:
        r = region
        x0, y0 = max(x0, min(r[0], r[2]) + origin[0]), max(y0, min(r[1], r[3]) + origin[1])
        x1, y1 = min(x1, max(r[0], r[2]) + origin[0]), min(y1, max(r[1], r[3]) + origin[1])
    g = grid
    nx, ny = int((x1 - x0) / g) + 1, int((y1 - y0) / g) + 1
    if nx * ny * len(layers) > 60e6:
        raise KitError("Grid too fine for this extent (%d cells); use a larger --grid or a region" % (nx * ny), 2)
    pads = geo["pads"]
    masks = {}
    for ln in layers:
        m = np.zeros((ny, nx), bool)
        lay = geo["layers"][ln]
        for conts in lay["zones"] + lay["items"]:
            m |= raster(np, conts, x0, y0, nx, ny, g)
        for p in pads:
            if ln in p["shapes"]:
                m |= raster(np, p["shapes"][ln], x0, y0, nx, ny, g)
        masks[ln] = m
    idx, n = {}, 0
    for ln in layers:
        a = -np.ones((ny, nx), int)
        k = int(masks[ln].sum())
        a[masks[ln]] = np.arange(n, n + k)
        idx[ln], n = a, n + k
    rows, cols, vals = [], [], []
    gsl = {ln: tcu[ln] / RHO for ln in layers}

    def link(i, j, gg):
        rows.extend([i, j, i, j]); cols.extend([i, j, j, i]); vals.extend([gg, gg, -gg, -gg])
    edges = {}
    for ln in layers:
        a = idx[ln]
        h = (a[:, :-1] >= 0) & (a[:, 1:] >= 0)
        v = (a[:-1, :] >= 0) & (a[1:, :] >= 0)
        edges[ln] = ((a[:, :-1][h], a[:, 1:][h]), (a[:-1, :][v], a[1:, :][v]))
        for p_, q_ in edges[ln]:
            rows.extend(np.concatenate([p_, q_, p_, q_])); cols.extend(np.concatenate([p_, q_, q_, p_]))
            vals.extend(np.concatenate([np.full(len(p_), gsl[ln])] * 2 + [np.full(len(p_), -gsl[ln])] * 2))

    def cell(ln, x, y):
        i, j = int((x - x0) / g), int((y - y0) / g)
        return idx[ln][j, i] if 0 <= i < nx and 0 <= j < ny and idx[ln][j, i] >= 0 else None
    t_plate = plating_mm * 1e-3
    barrels = [("via", v["x"], v["y"], v["drill"]) for v in geo["vias"]] + \
              [("%s.%s" % (p["ref"], p["number"]), p["x"], p["y"], p["drill"]) for p in pads if p["drill"] > 0]
    bsegs = []
    for lab, x, y, d in barrels:
        ls = [ln for ln in layers if cell(ln, x, y) is not None]
        segs = []
        for la, lb in zip(ls, ls[1:]):
            gg = 1 / (RHO * abs(zc[lb] - zc[la]) * 1e-3 / (math.pi * d * 1e-3 * t_plate))
            na, nb = cell(la, x, y), cell(lb, x, y)
            link(na, nb, gg)
            segs.append((na, nb, gg))
        bsegs.append((lab, x, y, d, segs))
    term = {}

    def terminal(key, padlist):
        nonlocal n
        tid, hit = n, 0
        n += 1
        for ref, num in padlist:
            found = [p for p in pads if p["ref"] == ref and p["number"] == str(num)]
            if not found:
                raise KitError("Terminal %s: pad %s.%s is not on net %s" % (key, ref, num, case["net"]), 13)
            for p in found:
                for ln in layers:
                    if ln in p["shapes"]:
                        pm = raster(np, p["shapes"][ln], x0, y0, nx, ny, g) & masks[ln]
                        for k in idx[ln][pm]:
                            link(tid, k, G_TERM)
                            hit += 1
        if not hit:
            raise KitError("Terminal %s: no copper cells in the model region" % key, 13)
        term[key] = tid
    terminal("source", case["source"])
    sinks = []
    for s, cur in zip(case["sinks"], currents):
        terminal(s["label"], s["pads"])
        sinks.append((s["label"], cur))
    A = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    _, lab = connected_components(A != 0, directed=False)
    comp = lab[term["source"]]
    keep = np.where(lab == comp)[0]
    pos = -np.ones(n, int)
    pos[keep] = np.arange(len(keep))
    Ak = A[keep][:, keep].tocsr()
    I = np.zeros(len(keep))
    unconnected = []
    for label, cur in sinks:
        if lab[term[label]] != comp:
            unconnected.append(label)
        else:
            I[pos[term[label]]] -= cur
    s = pos[term["source"]]
    free = np.array([i for i in range(len(keep)) if i != s])
    V = np.zeros(len(keep))
    V[free] = spl.spsolve(Ak[free][:, free].tocsc(), I[free])
    Vn = np.full(n, np.nan)
    Vn[keep] = V
    loss = 0.0
    for ln in layers:
        for aa, bb in edges[ln]:
            dv = Vn[aa] - Vn[bb]
            loss += float(np.nansum(dv * dv * gsl[ln]))
    rep = []
    for label, x, y, d, segs in bsegs:
        if segs and not np.isnan(Vn[segs[0][0]]):
            cur = max(abs(Vn[na] - Vn[nb]) * gg for na, nb, gg in segs)
            rep.append({"barrel": label, "x": round(x - origin[0], 3), "y": round(y - origin[1], 3), "drill": d,
                        "current_a": round(float(cur), 4)})
    rep.sort(key=lambda r: -r["current_a"])
    density, maps = {}, {}
    for ln in layers:
        a = idx[ln]
        Vg = np.where(a >= 0, Vn[np.maximum(a, 0)], np.nan)
        ix, iy = np.zeros((ny, nx)), np.zeros((ny, nx))
        dx = np.nan_to_num((Vg[:, :-1] - Vg[:, 1:]) * gsl[ln])
        dy = np.nan_to_num((Vg[:-1, :] - Vg[1:, :]) * gsl[ln])
        ix[:, :-1] += dx / 2; ix[:, 1:] += dx / 2
        iy[:-1, :] += dy / 2; iy[1:, :] += dy / 2
        lin = np.hypot(ix, iy) / g
        lin[a < 0] = 0
        padm = np.zeros((ny, nx), bool)
        for p in pads:
            if ln in p["shapes"]:
                padm |= raster(np, p["shapes"][ln], x0, y0, nx, ny, g)
        shown = []
        for o in np.argsort(lin, axis=None)[::-1]:
            j, i = divmod(int(o), nx)
            if padm[j, i] or lin[j, i] <= 0:
                continue
            x, y = x0 + (i + 0.5) * g, y0 + (j + 0.5) * g
            if all(math.hypot(x - sx, y - sy) > 1.5 for sx, sy, _ in shown):
                shown.append((x, y, float(lin[j, i])))
            if len(shown) >= 6:
                break
        density[ln] = [{"x": round(x - origin[0], 2), "y": round(y - origin[1], 2), "a_per_mm": round(v, 3)}
                       for x, y, v in shown]
        rgb = np.zeros((ny, nx, 3))
        rgb[masks[ln]] = (70, 70, 70)
        for k in range(len(STEPS)):
            lo = STEPS[k - 1][0] if k else 0.05
            rgb[masks[ln] & (lin >= lo)] = STEPS[k][1]
        rgb[padm & masks[ln]] = (200, 200, 200)
        sc = max(1, int(round(0.1 / g * 4)))
        rgb = np.repeat(np.repeat(rgb, sc, 0), sc, 1)
        name = "%s_%s.png" % (case["id"], ln.replace(".", "_"))
        png(folder / name, rgb)
        maps[ln] = {"file": name, "sha256": sha256(folder / name)}
    return {"cells": int(n), "grid_mm": g,
            "region": [round(x0 - origin[0], 3), round(y0 - origin[1], 3), round(x0 + nx * g - origin[0], 3),
                       round(y0 + ny * g - origin[1], 3)],
            "sinks": [{"label": label, "current_a": cur,
                       "potential_mv": None if label in unconnected else round(float(Vn[term[label]]) * 1e3, 3),
                       "resistance_mohm": None if label in unconnected or not cur
                       else round(abs(float(Vn[term[label]]) / cur) * 1e3, 3)} for label, cur in sinks],
            "unconnected": unconnected, "copper_loss_w": round(loss, 4),
            "barrels_over_50ma": [r for r in rep if r["current_a"] > 0.05], "density": density, "maps": maps,
            "map_legend": "grey < 0.05 A/mm, light grey pads; dark blue < 0.5, blue < 1, green < 2, yellow < 3, "
                          "orange < 5, red >= 5 A/mm of copper width"}


def analyze(project, case_ids=None, grid=0.1, region=None):
    import tempfile
    from tools.quality import board_model

    root = Path(project).resolve()
    board = project_files(root)[2]
    cases_path, data = load_cases(root)
    register = Assumptions(root)
    plating = register.get(data.get("plating"), "mm", strict=True)
    tcu, zc = stackup(board.read_text())
    bb = board_model.load(board)["outline_bbox"] or (0.0, 0.0, 0.0, 0.0)
    parent = root / "qa/generated/power-paths"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="run-", dir=parent))
    try:
        before = sha256(board)
        results = []
        selected = [c for c in data["cases"] if not case_ids or c.get("id") in case_ids]
        if case_ids and len(selected) != len(set(case_ids)):
            raise KitError("Unknown case id(s): %s" % sorted(set(case_ids) - {c.get("id") for c in selected}), 2)
        if not selected:
            raise KitError("No cases in %s" % cases_path, 13)
        for case in selected:
            for key in ("id", "net", "layers", "source", "sinks"):
                if not case.get(key):
                    raise KitError("Case %r needs %s" % (case.get("id"), key), 13)
            currents = []
            for s in case["sinks"]:
                value = register.get(s.get("current"), "A")
                if s.get("direction", "out") not in ("out", "in"):
                    raise KitError("Sink %s: direction must be out or in" % s.get("label"), 13)
                currents.append(value if s.get("direction", "out") == "out" else -value)
            geo = extract(board, case["net"], case["layers"], folder)
            r = solve(geo, case, currents, plating, tcu, zc, grid, region, bb[:2], folder)
            results.append(dict(r, id=case["id"], net=case["net"], layers=case["layers"],
                                source=["%s.%s" % tuple(p) for p in case["source"]]))
        (folder / "geometry.json").unlink(missing_ok=True)
        (folder / "extract.json").unlink(missing_ok=True)
        register.unchanged()
        if sha256(board) != before:
            raise KitError("Board changed during the run; repeat on a stable board.", 13)
        result = {"status": "ESTIMATE" if not any(r["unconnected"] for r in results) else "UNCONNECTED_SINKS",
                  "created": now(), "board": str(board), "board_sha256": before, "cases_file": str(cases_path),
                  "cases_sha256": sha256(cases_path), "stackup_copper_um": {k: round(v * 1e6, 2) for k, v in tcu.items()},
                  "plating_mm": plating, "datum": "outline top-left corner, mm, y down", "results": results,
                  "basis": register.basis(),
                  "limitations": ["DC estimate at 20 degC from stated copper thickness and plating; no temperature "
                                  "rise, plating tolerance, solder fill, AC effects or contact resistance.",
                                  "Grid resolution limits narrow necks; compare a finer grid before relying on a value.",
                                  "Not a measurement; confirm drops and temperatures on the built board."]}
    except Exception as exc:
        write_json(folder / "result.json", {"status": "FAILED", "created": now(), "directory": str(folder),
                                            "error": str(exc)})
        if isinstance(exc, KitError):
            raise KitError("%s (failed run: %s)" % (exc, folder), exc.exit_code) from exc
        raise
    result["directory"] = str(folder)
    write_json(folder / "result.json", result)
    return result
