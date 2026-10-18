"""Board geometry for thermal analysis, read from a .kicad_pcb file (read-only).

Extracts the Edge.Cuts outline, outer-layer copper (tracks, arcs, pads, filled
zones), vias and plated holes, footprint placement and the stack-up, then
rasterizes them onto a regular grid with 2x2 supersampling so each cell gets a
fractional copper coverage.

Coordinates are KiCad board millimetres (y grows downward).
"""

import math
from pathlib import Path

from tools.core import sexpr
from tools.core.common import KitError

OUTER = ("F.Cu", "B.Cu")
DEFAULT_COPPER_MM = 0.035  # 1 oz/ft²; used only when the board has no stack-up


def _np():
    try:
        import numpy
    except ImportError:
        raise KitError("Thermal analysis needs numpy and scipy; run ./install_template.command "
                       "(installs requirements.txt into .venv) and use scripts/kit.", 19)
    return numpy


def _xy(node, name="at"):
    c = sexpr.child(node, name)
    return (float(c[1]), float(c[2])) if c else (0.0, 0.0)


def _angle(node):
    c = sexpr.child(node, "at")
    return float(c[3]) if c and len(c) > 3 else 0.0


def rotate(lx, ly, degrees):
    """KiCad orientation: positive angles turn counter-clockwise on screen (y down)."""
    a = math.radians(degrees)
    return lx * math.cos(a) + ly * math.sin(a), -lx * math.sin(a) + ly * math.cos(a)


def arc_points(start, mid, end, step_deg=5.0):
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        return [start, end]
    ux = ((x1 ** 2 + y1 ** 2) * (y2 - y3) + (x2 ** 2 + y2 ** 2) * (y3 - y1) + (x3 ** 2 + y3 ** 2) * (y1 - y2)) / d
    uy = ((x1 ** 2 + y1 ** 2) * (x3 - x2) + (x2 ** 2 + y2 ** 2) * (x1 - x3) + (x3 ** 2 + y3 ** 2) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for x, y in (start, mid, end))

    def sweep(a, b):
        return (b - a) % (2 * math.pi)

    total = sweep(a1, a3)
    if sweep(a1, a2) > total:  # mid lies on the other way round
        total -= 2 * math.pi
    n = max(2, int(abs(math.degrees(total)) / step_deg) + 1)
    return [(ux + r * math.cos(a1 + total * i / n), uy + r * math.sin(a1 + total * i / n)) for i in range(n + 1)]


def _circle(cx, cy, r, n=72):
    return [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _chain(polylines, tol=1e-3):
    """Join open Edge.Cuts primitives into closed loops."""
    loops, pending = [], [list(p) for p in polylines]
    while pending:
        loop = pending.pop(0)
        changed = True
        while changed and math.dist(loop[0], loop[-1]) > tol:
            changed = False
            for i, p in enumerate(pending):
                if math.dist(loop[-1], p[0]) <= tol:
                    loop += p[1:]
                elif math.dist(loop[-1], p[-1]) <= tol:
                    loop += p[::-1][1:]
                elif math.dist(loop[0], p[-1]) <= tol:
                    loop = p[:-1] + loop
                elif math.dist(loop[0], p[0]) <= tol:
                    loop = p[::-1][:-1] + loop
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if math.dist(loop[0], loop[-1]) <= tol and len(loop) >= 4:
            loops.append(loop[:-1])
        else:
            raise KitError("Board outline (Edge.Cuts) is not closed near (%.3f, %.3f) mm." % loop[-1], 13)
    return loops


def _shape_polyline(node):
    kind = node[0]
    if kind in ("gr_line", "fp_line"):
        return [_xy(node, "start"), _xy(node, "end")], False
    if kind in ("gr_arc", "fp_arc"):
        return arc_points(_xy(node, "start"), _xy(node, "mid"), _xy(node, "end")), False
    if kind in ("gr_rect", "fp_rect"):
        (x1, y1), (x2, y2) = _xy(node, "start"), _xy(node, "end")
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], True
    if kind in ("gr_circle", "fp_circle"):
        (cx, cy), (ex, ey) = _xy(node, "center"), _xy(node, "end")
        return _circle(cx, cy, math.hypot(ex - cx, ey - cy)), True
    if kind in ("gr_poly", "fp_poly"):
        pts = sexpr.child(node, "pts") or []
        return [(float(p[1]), float(p[2])) for p in sexpr.children(pts, "xy")], True
    if kind in ("gr_curve", "fp_curve"):
        pts = [(float(p[1]), float(p[2])) for p in sexpr.children(sexpr.child(node, "pts") or [], "xy")]
        if len(pts) == 4:
            return [_bezier(pts, i / 16) for i in range(17)], False
    return None, False


def _bezier(p, t):
    return tuple((1 - t) ** 3 * p[0][k] + 3 * (1 - t) ** 2 * t * p[1][k] + 3 * (1 - t) * t ** 2 * p[2][k]
                 + t ** 3 * p[3][k] for k in (0, 1))


def _layers(node):
    c = sexpr.child(node, "layers")
    names = [str(x) for x in c[1:]] if c else []
    single = sexpr.value(node, "layer")
    if single:
        names.append(str(single))
    out = set()
    for n in names:
        if n in ("*.Cu", "F&B.Cu"):
            out.update(OUTER)
        elif n in OUTER:
            out.add(n)
    return out


def load_board(path):
    """Parse everything the thermal model needs from one .kicad_pcb."""
    path = Path(path)
    try:
        tree = sexpr.load(path)
    except (OSError, sexpr.ParseError) as exc:
        raise KitError("Cannot read board %s: %s" % (path, exc), 13)
    warnings = []
    general = sexpr.child(tree, "general") or []
    thickness = float(sexpr.value(general, "thickness", 1.6))
    copper_names = [str(l[1]) for l in (sexpr.child(tree, "layers") or [])[1:]
                    if isinstance(l, list) and len(l) > 1 and str(l[1]).endswith(".Cu")]
    copper_thickness, stackup_source = {}, "board stack-up"
    stackup = sexpr.child(sexpr.child(tree, "setup") or [], "stackup")
    for layer in sexpr.children(stackup or [], "layer"):
        if layer[1] in OUTER and sexpr.value(layer, "thickness") is not None:
            copper_thickness[layer[1]] = float(sexpr.value(layer, "thickness"))
    if set(copper_thickness) != set(OUTER):
        stackup_source = "default %.3f mm (no stack-up in board)" % DEFAULT_COPPER_MM
        copper_thickness = {l: copper_thickness.get(l, DEFAULT_COPPER_MM) for l in OUTER}
    inner = [n for n in copper_names if n not in OUTER]
    if inner:
        warnings.append("%d inner copper layer(s) not modelled (phase 1): lateral spreading is underestimated, "
                        "so temperatures are likely overestimated." % len(inner))

    outline, open_parts = [], []
    for node in tree[1:]:
        if isinstance(node, list) and node and str(node[0]).startswith("gr_") and sexpr.value(node, "layer") == "Edge.Cuts":
            pts, closed = _shape_polyline(node)
            if pts:
                (outline if closed else open_parts).append(pts)
    outline += _chain(open_parts) if open_parts else []
    if not outline:
        raise KitError("Board has no Edge.Cuts outline; draw one before thermal analysis.", 13)

    tracks, vias, zones, footprints = [], [], [], {}
    for node in tree[1:]:
        if not isinstance(node, list) or not node:
            continue
        kind = node[0]
        if kind in ("segment", "arc") and sexpr.value(node, "layer") in OUTER:
            pts = [_xy(node, "start"), _xy(node, "end")] if kind == "segment" else arc_points(
                _xy(node, "start"), _xy(node, "mid"), _xy(node, "end"))
            width = float(sexpr.value(node, "width", 0.2))
            for a, b in zip(pts, pts[1:]):
                tracks.append((sexpr.value(node, "layer"), a, b, width))
        elif kind == "via":
            x, y = _xy(node)
            vias.append({"x": x, "y": y, "size": float(sexpr.value(node, "size", 0.6)),
                         "drill": float(sexpr.value(node, "drill", 0.3)), "layers": _layers(node)})
        elif kind == "zone":
            for poly in sexpr.children(node, "filled_polygon"):
                layer = sexpr.value(poly, "layer")
                if layer in OUTER:
                    pts = [(float(p[1]), float(p[2])) for p in sexpr.children(sexpr.child(poly, "pts") or [], "xy")]
                    zones.append((layer, pts))
            if not sexpr.children(node, "filled_polygon") and _layers(node):
                warnings.append("Zone on %s has no fill saved; fill zones in KiCad (B) and save for its copper to "
                                "count." % "/".join(sorted(_layers(node))))
        elif kind == "footprint":
            ref = sexpr.properties(node).get("Reference", "?")
            fx, fy = _xy(node)
            fa = _angle(node)
            side = "B.Cu" if sexpr.value(node, "layer") == "B.Cu" else "F.Cu"
            pads, court = [], []
            for pad in sexpr.children(node, "pad"):
                lx, ly = _xy(pad)
                dx, dy = rotate(lx, ly, fa)
                size = sexpr.child(pad, "size")
                drill = sexpr.child(pad, "drill")
                dval = 0.0
                if drill is not None:
                    nums = [float(v) for v in drill[1:] if isinstance(v, str) and _is_num(v)]
                    dval = min(nums) if nums else 0.0
                pads.append({"x": fx + dx, "y": fy + dy, "w": float(size[1]), "h": float(size[2]),
                             "angle": _angle(pad), "shape": str(pad[3]) if len(pad) > 3 else "rect",
                             "layers": _layers(pad), "drill": dval, "plated": str(pad[2]) == "thru_hole"})
            for g in node[1:]:
                if isinstance(g, list) and g and sexpr.value(g, "layer") in ("F.CrtYd", "B.CrtYd"):
                    pts, _ = _shape_polyline(g)
                    for px, py in pts or []:
                        rx, ry = rotate(px, py, fa)
                        court.append((fx + rx, fy + ry))
            footprints[ref] = {"reference": ref, "side": side, "x": fx, "y": fy, "pads": pads, "courtyard": court}
    return {"path": str(path), "thickness_mm": thickness, "copper_mm": copper_thickness,
            "copper_source": stackup_source, "copper_layers": copper_names, "outline": outline,
            "tracks": tracks, "vias": vias, "zones": zones, "footprints": footprints, "warnings": warnings}


def _is_num(text):
    try:
        float(text)
        return True
    except ValueError:
        return False


# -- rasterization -------------------------------------------------------------
class Grid:
    """Cell-centred grid over the board bounding box; `fine` has sub×sub samples per cell."""

    def __init__(self, outline, cell_mm, sub=2):
        np = _np()
        pts = np.array([p for loop in outline for p in loop])
        self.x0, self.y0 = pts[:, 0].min(), pts[:, 1].min()
        self.cell, self.sub = float(cell_mm), sub
        self.nx = max(1, int(math.ceil((pts[:, 0].max() - self.x0) / self.cell)))
        self.ny = max(1, int(math.ceil((pts[:, 1].max() - self.y0) / self.cell)))
        self.fine = self.cell / sub
        self.fx = self.x0 + (np.arange(self.nx * sub) + 0.5) * self.fine
        self.fy = self.y0 + (np.arange(self.ny * sub) + 0.5) * self.fine

    @property
    def xc(self):
        return self.x0 + (_np().arange(self.nx) + 0.5) * self.cell

    @property
    def yc(self):
        return self.y0 + (_np().arange(self.ny) + 0.5) * self.cell

    def empty(self):
        return _np().zeros((self.ny * self.sub, self.nx * self.sub), dtype=bool)

    def coverage(self, fine):
        np = _np()
        return fine.reshape(self.ny, self.sub, self.nx, self.sub).mean(axis=(1, 3)).astype(np.float64)

    def window(self, xmin, ymin, xmax, ymax):
        np = _np()
        i0 = max(0, int((ymin - self.y0) / self.fine) - 1)
        i1 = min(len(self.fy), int((ymax - self.y0) / self.fine) + 2)
        j0 = max(0, int((xmin - self.x0) / self.fine) - 1)
        j1 = min(len(self.fx), int((xmax - self.x0) / self.fine) + 2)
        if i0 >= i1 or j0 >= j1:
            return None
        X, Y = np.meshgrid(self.fx[j0:j1], self.fy[i0:i1])
        return (slice(i0, i1), slice(j0, j1)), X, Y

    def cell_of(self, x, y):
        j, i = int((x - self.x0) / self.cell), int((y - self.y0) / self.cell)
        return (i, j) if 0 <= i < self.ny and 0 <= j < self.nx else None


def fill_polygons(grid, target, loops):
    """Even-odd scanline fill of closed loops into a fine boolean array."""
    np = _np()
    ys = grid.fy
    rows, xs = [], []
    for loop in loops:
        p = np.asarray(loop, dtype=float)
        q = np.roll(p, -1, axis=0)
        for (x1, y1), (x2, y2) in zip(p, q):
            if y1 == y2:
                continue
            lo, hi = min(y1, y2), max(y1, y2)
            r = np.nonzero((ys >= lo) & (ys < hi))[0]
            if r.size:
                rows.append(r)
                xs.append(x1 + (ys[r] - y1) * (x2 - x1) / (y2 - y1))
    if not rows:
        return
    rows, xs = np.concatenate(rows), np.concatenate(xs)
    order = np.lexsort((xs, rows))
    rows, xs = rows[order], xs[order]
    diff = np.zeros((target.shape[0], target.shape[1] + 1), dtype=np.int32)
    # Crossings come in pairs per row (even-odd rule).
    starts, ends = slice(0, None, 2), slice(1, None, 2)
    r, xa, xb = rows[starts], xs[starts], xs[ends]
    ca = np.clip(np.ceil((xa - grid.x0) / grid.fine - 0.5), 0, target.shape[1]).astype(int)
    cb = np.clip(np.floor((xb - grid.x0) / grid.fine - 0.5) + 1, 0, target.shape[1]).astype(int)
    keep = cb > ca
    np.add.at(diff, (r[keep], ca[keep]), 1)
    np.add.at(diff, (r[keep], cb[keep]), -1)
    target |= np.cumsum(diff, axis=1)[:, :-1] > 0


def draw_segment(grid, target, a, b, width):
    np = _np()
    r = width / 2
    win = grid.window(min(a[0], b[0]) - r, min(a[1], b[1]) - r, max(a[0], b[0]) + r, max(a[1], b[1]) + r)
    if not win:
        return
    sl, X, Y = win
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    t = np.clip(((X - a[0]) * dx + (Y - a[1]) * dy) / L2, 0, 1) if L2 else 0
    target[sl] |= (X - a[0] - t * dx) ** 2 + (Y - a[1] - t * dy) ** 2 <= r * r


def draw_pad(grid, target, pad):
    np = _np()
    reach = math.hypot(pad["w"], pad["h"]) / 2
    win = grid.window(pad["x"] - reach, pad["y"] - reach, pad["x"] + reach, pad["y"] + reach)
    if not win:
        return
    sl, X, Y = win
    # Pad-local frame: undo the absolute pad orientation.
    u, v = rotate(X - pad["x"], Y - pad["y"], -pad["angle"])
    w, h = pad["w"] / 2, pad["h"] / 2
    if pad["shape"] == "circle":
        inside = u * u + v * v <= w * w
    elif pad["shape"] == "oval":
        r = min(w, h)
        cu = np.clip(u, -(w - r), w - r)
        cv = np.clip(v, -(h - r), h - r)
        inside = (u - cu) ** 2 + (v - cv) ** 2 <= r * r
    else:  # rect, roundrect, trapezoid, custom: bounding rectangle (first order)
        inside = (np.abs(u) <= w) & (np.abs(v) <= h)
    target[sl] |= inside


def rasterize(board, cell_mm):
    """Board mask and per-layer fractional copper coverage on a common grid."""
    grid = Grid(board["outline"], cell_mm)
    fine_board = grid.empty()
    fill_polygons(grid, fine_board, board["outline"])
    copper = {layer: grid.empty() for layer in OUTER}
    for layer, a, b, width in board["tracks"]:
        draw_segment(grid, copper[layer], a, b, width)
    for layer, pts in board["zones"]:
        fill_polygons(grid, copper[layer], [pts])
    for via in board["vias"]:
        for layer in via["layers"] or OUTER:
            draw_pad(grid, copper[layer], {"x": via["x"], "y": via["y"], "w": via["size"], "h": via["size"],
                                           "angle": 0, "shape": "circle"})
    for fp in board["footprints"].values():
        for pad in fp["pads"]:
            for layer in pad["layers"]:
                draw_pad(grid, copper[layer], pad)
    mask = grid.coverage(fine_board) >= 0.5
    return grid, mask, {layer: grid.coverage(copper[layer]) * mask for layer in OUTER}


def footprint_weights(grid, fp, mask):
    """Cell weights where a component's heat enters the board: its pads on its side,
    else its courtyard bounding box."""
    np = _np()
    fine = grid.empty()
    for pad in fp["pads"]:
        if fp["side"] in pad["layers"]:
            draw_pad(grid, fine, pad)
    weights = grid.coverage(fine) * mask
    basis = "pads"
    if weights.sum() == 0 and fp["courtyard"]:
        pts = np.array(fp["courtyard"])
        fill_polygons(grid, fine, [[(pts[:, 0].min(), pts[:, 1].min()), (pts[:, 0].max(), pts[:, 1].min()),
                                    (pts[:, 0].max(), pts[:, 1].max()), (pts[:, 0].min(), pts[:, 1].max())]])
        weights, basis = grid.coverage(fine) * mask, "courtyard"
    if weights.sum() == 0:
        return None, "none"
    return weights / weights.sum(), basis
