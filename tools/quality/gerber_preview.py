"""Preview images drawn from exported Gerber and Excellon files (what the fabricator receives).

Reads `fabrication/gerbers` and `fabrication/drill` of an export and writes one SVG per copper, mask,
silkscreen and paste layer, a drill map (plated blue, non-plated red) and top/bottom composites. PNGs are
added when `rsvg-convert` is available. Bottom views are mirrored (seen from below).

Supported subset (what KiCad 10.0.7 writes): FS/MO metric, apertures C/R/O and macros with primitives
1/4/20/21 (arithmetic in $n parameters), D01/D02/D03, G01/G02/G03 with G75, regions G36/G37, LPD/LPC;
Excellon tools with X/Y hits and G85 slots. Anything else stops with an error instead of being skipped.
Review images, not source; they do not replace the fabricator's CAM preview.
"""
import ast
import math
import operator
from pathlib import Path
import re
import shutil

from tools.core.common import KitError, now, run, sha256

LAYERS = ("F_Cu", "In1_Cu", "In2_Cu", "In3_Cu", "In4_Cu", "B_Cu", "F_Mask", "B_Mask", "F_Silkscreen",
          "B_Silkscreen", "F_Paste", "B_Paste", "Edge_Cuts")
COLOURS = {"F_Cu": "#d23c3c", "In1_Cu": "#c8a000", "In2_Cu": "#30a050", "In3_Cu": "#a050c0", "In4_Cu": "#40a0a0",
           "B_Cu": "#3c78e6", "F_Mask": "#b060d0", "B_Mask": "#b060d0", "F_Silkscreen": "#ffffff",
           "B_Silkscreen": "#ffffff", "F_Paste": "#a0a0a0", "B_Paste": "#a0a0a0"}
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}


def macro_value(expr, params):
    """Gerber macro arithmetic ($n, + - x /, parentheses) without eval."""
    text = re.sub(r"\$(\d+)", lambda m: "(%r)" % params[int(m.group(1)) - 1], expr).replace("x", "*").replace("X", "*")

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
            return _OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return -ev(node.operand) if isinstance(node.op, ast.USub) else ev(node.operand)
        raise KitError("Unsupported Gerber macro expression: %r" % expr, 13)

    try:
        return ev(ast.parse(text, mode="eval"))
    except (SyntaxError, IndexError) as exc:
        raise KitError("Bad Gerber macro expression %r: %s" % (expr, exc), 13)


def _num(s, fmt):
    neg = s.startswith("-")
    v = int(s.lstrip("+-")) / 10 ** fmt
    return -v if neg else v


class Gerber:
    def __init__(self, path):
        self.name, self.fmt, self.ap, self.macros, self.items = Path(path).name, 6, {}, {}, []
        self._parse(Path(path).read_text(errors="replace"))

    def _error(self, what):
        raise KitError("%s: %s" % (self.name, what), 13)

    def _parse(self, text):
        x = y = 0.0
        cur, mode, region, pol, path = None, "G01", False, "D", []
        for blk in re.findall(r"%[^%]*%|[^*%\s][^*%]*\*", text):
            b = blk.strip("%").strip()
            if blk.startswith("%"):
                self._ext(b)
                if b.startswith("LP"):
                    pol = b[2]
                continue
            b = b.rstrip("*")
            if b.startswith("G04") or b in ("G75", "M02"):
                continue
            if b.startswith("G36"):
                region, path = True, []
                continue
            if b.startswith("G37"):
                if path:
                    self.items.append(("region", pol, path))
                region, path = False, []
                continue
            if re.match(r"^D(\d{2,})$", b) and int(b[1:]) >= 10:
                cur = int(b[1:])
                continue
            m = re.match(r"^(G0[123])?(?:X([+-]?\d+))?(?:Y([+-]?\d+))?(?:I([+-]?\d+))?(?:J([+-]?\d+))?(D0[123])?$", b)
            if not m:
                self._error("unsupported Gerber block %r" % b)
            g, sx, sy, si, sj, d = m.groups()
            mode = g or mode
            nx = _num(sx, self.fmt) if sx else x
            ny = _num(sy, self.fmt) if sy else y
            i = _num(si, self.fmt) if si else 0.0
            j = _num(sj, self.fmt) if sj else 0.0
            if d == "D02" or (d is None and region and not (sx or sy)):
                if region and path:
                    self.items.append(("region", pol, path))
                path = [("M", nx, ny)] if region else []
            elif d == "D01" or (d is None and (sx or sy)):
                seg = ("L", nx, ny) if mode == "G01" else ("A", nx, ny, x + i, y + j, mode == "G02", x, y)
                if region:
                    path = path or [("M", x, y)]
                    path.append(seg)
                else:
                    if cur not in self.ap:
                        self._error("draw without a defined aperture")
                    self.items.append(("draw", pol, cur, x, y, seg))
            elif d == "D03":
                if cur not in self.ap:
                    self._error("flash without a defined aperture")
                self.items.append(("flash", pol, cur, nx, ny))
            x, y = nx, ny

    def _ext(self, b):
        if b.startswith("FS"):
            m = re.match(r"FSLAX(\d)(\d)Y\d\d", b.rstrip("*"))
            if not m:
                self._error("unsupported format %r" % b)
            self.fmt = int(m.group(2))
        elif b.startswith("MO") and "MM" not in b:
            self._error("only metric Gerber supported")
        elif b.startswith("AM"):
            lines = [l.strip() for l in b.split("*") if l.strip()]
            self.macros[lines[0][2:]] = [l for l in lines[1:] if not l.startswith("0")]
        elif b.startswith("AD"):
            m = re.match(r"ADD(\d+)([A-Za-z_][A-Za-z_0-9.]*),?([^*]*)\*", b)
            if not m:
                self._error("bad aperture definition %r" % b)
            self.ap[int(m.group(1))] = (m.group(2), [float(v) for v in m.group(3).split("X") if v])
        elif b.startswith("IP") and "POS" not in b:
            self._error("negative image polarity not supported")
        elif b.startswith(("LM", "LR", "LS", "SR")):
            self._error("unsupported transform %s" % b[:2])


def _rot(a, b, deg):
    r = math.radians(deg)
    return a * math.cos(r) - b * math.sin(r), a * math.sin(r) + b * math.cos(r)


def _flash(ger, code, x, y, col):
    kind, p = ger.ap[code]
    Y = -y
    if kind == "C":
        return '<circle cx="%.4f" cy="%.4f" r="%.4f" fill="%s"/>' % (x, Y, p[0] / 2, col)
    if kind in ("R", "O"):
        rx = ' rx="%.4f"' % (min(p[:2]) / 2) if kind == "O" else ""
        return '<rect x="%.4f" y="%.4f" width="%.4f" height="%.4f"%s fill="%s"/>' % (
            x - p[0] / 2, Y - p[1] / 2, p[0], p[1], rx, col)
    if kind in ger.macros:
        out = []
        for prim in ger.macros[kind]:
            f = prim.split(",")
            c = int(f[0])
            v = [macro_value(e, p) for e in f[1:]]
            if v[0] == 0:
                raise KitError("%s: macro clear exposure not supported" % ger.name, 13)
            if c == 1:
                out.append('<circle cx="%.4f" cy="%.4f" r="%.4f" fill="%s"/>' % (x + v[2], Y - v[3], v[1] / 2, col))
            elif c == 4:
                n, rot = int(v[1]), v[-1]
                pts = [_rot(v[2 + 2 * k], v[3 + 2 * k], rot) for k in range(n + 1)]
                out.append('<polygon points="%s" fill="%s"/>' % (" ".join("%.4f,%.4f" % (x + a, Y - b) for a, b in pts), col))
            elif c == 20:
                (x1, y1), (x2, y2) = _rot(v[2], v[3], v[6]), _rot(v[4], v[5], v[6])
                out.append('<line x1="%.4f" y1="%.4f" x2="%.4f" y2="%.4f" stroke="%s" stroke-width="%.4f"/>'
                           % (x + x1, Y - y1, x + x2, Y - y2, col, v[1]))
            elif c == 21:
                w, h, cx, cy, rot = v[1:6]
                pts = [_rot(cx + sx * w / 2, cy + sy * h / 2, rot) for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                out.append('<polygon points="%s" fill="%s"/>' % (" ".join("%.4f,%.4f" % (x + a, Y - b) for a, b in pts), col))
            else:
                raise KitError("%s: macro primitive %d not supported" % (ger.name, c), 13)
        return "".join(out)
    raise KitError("%s: aperture %s not supported" % (ger.name, kind), 13)


def _arc(seg):
    _, ex, ey, cx, cy, cw, sx, sy = seg
    r = math.hypot(sx - cx, sy - cy)
    a0, a1 = math.atan2(sy - cy, sx - cx), math.atan2(ey - cy, ex - cx)
    sweep = (a0 - a1) % (2 * math.pi) if cw else (a1 - a0) % (2 * math.pi)
    if sweep < 1e-9:  # full circle (G75)
        mx, my, f = 2 * cx - sx, 2 * cy - sy, 0 if cw else 1
        return "A%.4f,%.4f 0 0 %d %.4f,%.4f A%.4f,%.4f 0 0 %d %.4f,%.4f" % (r, r, f, mx, -my, r, r, f, ex, -ey)
    return "A%.4f,%.4f 0 %d %d %.4f,%.4f" % (r, r, 1 if sweep > math.pi else 0, 0 if cw else 1, ex, -ey)


def layer_svg(ger, col, clear="#101010"):
    out = []
    for it in ger.items:
        c = col if it[1] == "D" else clear
        if it[0] == "flash":
            out.append(_flash(ger, it[2], it[3], it[4], c))
        elif it[0] == "draw":
            _, _, code, x0, y0, seg = it
            kind, p = ger.ap[code]
            if kind != "C":
                raise KitError("%s: draw with non-circular aperture %s" % (ger.name, kind), 13)
            d = "M%.4f,%.4f " % (x0, -y0) + ("L%.4f,%.4f" % (seg[1], -seg[2]) if seg[0] == "L" else _arc(seg))
            out.append('<path d="%s" fill="none" stroke="%s" stroke-width="%.4f" stroke-linecap="round" '
                       'stroke-linejoin="round"/>' % (d, c, p[0]))
        else:
            d = ["M%.4f,%.4f" % (s[1], -s[2]) if s[0] == "M" else "L%.4f,%.4f" % (s[1], -s[2]) if s[0] == "L"
                 else _arc(s) for s in it[2]]
            out.append('<path d="%sZ" fill="%s"/>' % (" ".join(d), c))
    return "\n".join(out)


def drill_hits(path):
    """(x, y, diameter, plated, slot_end or None) for every hit/slot of one Excellon file."""
    tools, hits, cur, plating = {}, [], None, {}
    attr = "Plated"
    for line in Path(path).read_text(errors="replace").splitlines():
        if line.startswith(("; #@! TF.FileFunction", "; #@! TA.AperFunction")):
            attr = "NonPlated" if "NonPlated" in line else "Plated"
        m = re.match(r"^T(\d+)C([\d.]+)", line)
        if m:
            tools[int(m.group(1))], plating[int(m.group(1))] = float(m.group(2)), attr
            continue
        m = re.match(r"^T(\d+)$", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"^X([-\d.]+)Y([-\d.]+)(?:G85X([-\d.]+)Y([-\d.]+))?$", line)
        if m:
            if cur not in tools:
                raise KitError("%s: hit without a tool" % Path(path).name, 13)
            end = (float(m.group(3)), float(m.group(4))) if m.group(3) else None
            hits.append((float(m.group(1)), float(m.group(2)), tools[cur], plating[cur] == "Plated", end))
        elif re.match(r"^(G00|G01|M15|M16)", line):
            raise KitError("%s: routed drill paths not supported" % Path(path).name, 13)
    return hits


def _drill_svg(hits, colour=None):
    out = []
    for x, y, d, plated, end in hits:
        col = colour or ("#50c0ff" if plated else "#ff5050")
        if end:
            out.append('<line x1="%.4f" y1="%.4f" x2="%.4f" y2="%.4f" stroke="%s" stroke-width="%.4f" '
                       'stroke-linecap="round"/>' % (x, -y, end[0], -end[1], col, d))
        else:
            out.append('<circle cx="%.4f" cy="%.4f" r="%.4f" fill="%s"/>' % (x, -y, max(d / 2, 0.15 if colour is None else 0), col))
    return "".join(out)


def _write(body, box, scale, path, bg):
    x0, y0, x1, y1 = box
    path.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="%.3f %.3f %.3f %.3f">'
                    '<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="%s"/>%s</svg>'
                    % ((x1 - x0) * scale, (y1 - y0) * scale, x0, y0, x1 - x0, y1 - y0, x0, y0, x1 - x0, y1 - y0,
                       bg, body))
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        r = run([rsvg, "-o", path.with_suffix(".png"), path], timeout=300)
        if r["exit_code"]:
            raise KitError("rsvg-convert failed for %s: %s" % (path.name, r["stderr"][-300:]), 13)
    return path


def render(package, output, scale=10.0):
    package, output = Path(package), Path(output)
    gdir, ddir = package / "fabrication/gerbers", package / "fabrication/drill"
    if not gdir.is_dir():
        raise KitError("No fabrication/gerbers in %s" % package, 13)
    output.mkdir(parents=True, exist_ok=True)
    layers = {}
    for p in sorted(gdir.iterdir()):
        if p.suffix.startswith(".g") and p.suffix != ".gbrjob" and "-" in p.stem:
            name = p.stem.rsplit("-", 1)[1] if p.stem.rsplit("-", 1)[1] in LAYERS else p.stem.split("-", 1)[1]
            if name in LAYERS:
                layers[name] = Gerber(p)
    if "Edge_Cuts" not in layers:
        raise KitError("No Edge_Cuts Gerber in %s" % gdir, 13)
    hits = [h for f in sorted(ddir.glob("*.drl")) for h in drill_hits(f)]
    edge = layer_svg(layers["Edge_Cuts"], "#e8e8a0")
    pts = [(float(a), float(b)) for a, b in re.findall(r"(-?\d+\.\d+),(-?\d+\.\d+)", edge)]
    if not pts:
        raise KitError("Edge_Cuts Gerber has no drawn outline", 13)
    ex, ey = [p[0] for p in pts], [p[1] for p in pts]
    xs, ys = ex + [h[0] for h in hits], ey + [-h[1] for h in hits]
    box = (min(xs) - 2, min(ys) - 2, max(xs) + 2, max(ys) + 2)
    board = (min(ex), min(ey), max(ex) - min(ex), max(ey) - min(ey))
    holes = _drill_svg(hits, "#000")
    mirror = ('<g transform="translate(%.3f,0) scale(-1,1)">' % (box[0] + box[2]), "</g>")
    files = []
    for name, col in COLOURS.items():
        if name not in layers:
            continue
        body = layer_svg(layers[name], col) + edge + (holes if name.endswith("Cu") else "")
        if name.startswith("B_"):
            body = mirror[0] + body + mirror[1]
        files.append(_write(body, box, scale, output / ("gerber_%s.svg" % name), "#101010"))
    files.append(_write(_drill_svg(hits) + edge, box, scale, output / "gerber_drill.svg", "#101010"))
    for side, label in (("F", "top"), ("B", "bottom")):
        if not all("%s_%s" % (side, k) in layers for k in ("Cu", "Mask", "Silkscreen")):
            continue
        body = ('<rect x="%.3f" y="%.3f" width="%.3f" height="%.3f" fill="#1f5a32"/>' % board
                + layer_svg(layers["%s_Cu" % side], "#2f7a45") + layer_svg(layers["%s_Mask" % side], "#d8b25a")
                + layer_svg(layers["%s_Silkscreen" % side], "#f4f4f4") + holes + edge)
        if side == "B":
            body = mirror[0] + body + mirror[1]
        files.append(_write(body, box, scale, output / ("gerber_composite_%s.svg" % label), "#202020"))
    images = sorted(p for f in files for p in (f, f.with_suffix(".png")) if p.is_file())
    return {"status": "IMAGES_READY", "created": now(), "package": str(package), "output": str(output),
            "layers": {k: len(v.items) for k, v in sorted(layers.items())},
            "drill": {"hits": sum(1 for h in hits if not h[4]), "slots": sum(1 for h in hits if h[4]),
                      "non_plated": sum(1 for h in hits if not h[3]), "tool_sizes": len({h[2] for h in hits})},
            "png": bool(shutil.which("rsvg-convert")),
            "images": {p.name: sha256(p) for p in images}, "visual_review": "PENDING",
            "limitations": ["Drawn from the exported files with a subset parser; compare with the fabricator's "
                            "CAM preview before ordering.", "Bottom views are mirrored (seen from below)."]}
