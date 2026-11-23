"""1:1 mounting print and hole table read from the board (review sheet, not a drawing release).

Datum: top-left corner of the outline bounding box (Edge.Cuts centre lines), mm, x right, y down; the
same datum as `kit board diff`. Holes are the footprints given by reference, or by default every
footprint whose reference is H<number> or whose name contains "MountingHole"; diameter and position
come from their drilled pads. Optional washer/head diameters are drawn as circles around each hole.
Rule areas (board and footprint level) are drawn dashed; `bodies` draws the F.Fab/B.Fab or courtyard
outline of the named footprints (connectors, modules) so plug and tool access can be judged.

The sheet is an SVG at true scale (A4 or A3 landscape, chosen to fit) with two 100 mm check bars;
a PDF is added when `rsvg-convert` is available. Print at 100 % ("actual size") and measure both bars
before using the print for a fit check. Not a drawing release; chassis suitability needs a physical fit.
"""
import itertools
import math
from pathlib import Path
import re
import shutil

from tools.core.common import KitError, now, run, sha256
from tools.quality import board_model

PAGES = {"A4": (297.0, 210.0), "A3": (420.0, 297.0)}
MARGIN, BAR = 22.0, 100.0


def mounting_holes(board, refs=None):
    out = []
    for ref, fp in sorted(board["footprints"].items(), key=lambda kv: (len(kv[0]), kv[0])):
        if refs is not None and ref not in refs:
            continue
        if refs is None and not (re.fullmatch(r"H\d+", ref) or "MountingHole" in fp["footprint"]):
            continue
        drilled = [p for p in fp["pads"] if p["drill"] > 0]
        if not drilled:
            raise KitError("Mounting footprint %s has no drilled pad" % ref, 13)
        p = max(drilled, key=lambda q: q["drill"])
        out.append({"reference": ref, "x": p["x"], "y": p["y"], "diameter": p["drill"],
                    "plated": p["type"] == "thru_hole", "footprint": fp["footprint"]})
    if refs is not None:
        missing = sorted(set(refs) - {h["reference"] for h in out})
        if missing:
            raise KitError("Not on the board: %s" % ", ".join(missing), 13)
    return out


def _body(board, ref):
    fp = board["footprints"].get(ref)
    if not fp:
        raise KitError("Body footprint %s not on the board" % ref, 13)
    side = "F" if fp["side"] == "top" else "B"
    for layer in ("%s.Fab" % side, "%s.CrtYd" % side):
        lines = fp["graphics"].get(layer)
        if lines:
            return layer, lines
    raise KitError("%s has no fab or courtyard outline" % ref, 13)


def sheet(board_path, output, holes=None, washer=None, head=None, bodies=(), title=""):
    b = board_model.load(board_path)
    if not b["outline_bbox"]:
        raise KitError("Board has no Edge.Cuts outline", 13)
    x0, y0, x1, y1 = b["outline_bbox"]
    w, h = x1 - x0, y1 - y0
    hl = mounting_holes(b, holes)
    for item in hl:
        item["dx"], item["dy"] = round(item["x"] - x0, 4), round(item["y"] - y0, 4)
    page = next((n for n, (pw, ph) in PAGES.items() if w + 2 * MARGIN + 25 <= pw and h + 2 * MARGIN + 45 <= ph), None)
    if page is None:
        raise KitError("Board %.1f x %.1f mm does not fit A3 at 1:1 with margins" % (w, h), 13)
    pw, ph = PAGES[page]
    ox, oy = MARGIN + 18, MARGIN + 16           # page position of the datum

    def P(x, y):                                # board coordinates -> page
        return x - x0 + ox, y - y0 + oy

    s = ['<svg xmlns="http://www.w3.org/2000/svg" width="%gmm" height="%gmm" viewBox="0 0 %g %g">' % (pw, ph, pw, ph),
         '<rect width="%g" height="%g" fill="white"/>' % (pw, ph),
         '<style>text{font-family:Helvetica,Arial,sans-serif;fill:#111} .d{stroke:#1f4fd0;stroke-width:0.15;fill:none}'
         ' .t{fill:#1f4fd0;font-size:2.4px}</style>']
    for loop in b["outline_loops"]:
        s.append('<polygon points="%s" fill="#f4f4ec" stroke="#000" stroke-width="0.3"/>'
                 % " ".join("%.3f,%.3f" % P(*p) for p in loop))
    for z in b["zones"] + b["footprint_zones"]:
        if z["rule_area"] and z["outline"]:
            s.append('<polygon points="%s" fill="none" stroke="#c03030" stroke-width="0.2" stroke-dasharray="1,0.7"/>'
                     % " ".join("%.3f,%.3f" % P(*p) for p in z["outline"]))
    body_layers = {}
    for ref in bodies:
        layer, lines = _body(b, ref)
        body_layers[ref] = layer
        for pl in lines:
            s.append('<polyline points="%s" fill="none" stroke="#d07010" stroke-width="0.25"/>'
                     % " ".join("%.3f,%.3f" % P(*p) for p in pl))
        cx = sum(p[0] for pl in lines for p in pl) / sum(len(pl) for pl in lines)
        cy = sum(p[1] for pl in lines for p in pl) / sum(len(pl) for pl in lines)
        s.append('<text x="%.2f" y="%.2f" font-size="2.2" fill="#d07010" text-anchor="middle">%s</text>' % (P(cx, cy) + (ref,)))
    for item in hl:
        cx, cy = P(item["x"], item["y"])
        for d, style in ((head, 'stroke="#808080" stroke-width="0.15" stroke-dasharray="0.6,0.4"'),
                         (washer, 'stroke="#2a8a2a" stroke-width="0.2"')):
            if d:
                s.append('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="none" %s/>' % (cx, cy, d / 2, style))
        s.append('<circle cx="%.3f" cy="%.3f" r="%.3f" fill="white" stroke="#000" stroke-width="0.2"/>'
                 % (cx, cy, item["diameter"] / 2))
        s.append('<path d="M%.3f,%.3fh8M%.3f,%.3fv8" stroke="#000" stroke-width="0.12"/>' % (cx - 4, cy, cx, cy - 4))
        s.append('<text x="%.2f" y="%.2f" font-size="2.6">%s</text>' % (cx + 2.2, cy - 2.2, item["reference"]))
    # chain dimensions from the datum: one label per distinct coordinate, ticks outside the outline,
    # thin dotted extension lines to the hole centre
    for k, value in enumerate(sorted({item["dx"] for item in hl})):
        cx = ox + value
        s.append('<path class="d" d="M%.3f,%.3fV%.3f"/>' % (cx, oy - 5, oy))
        s.append('<text class="t" x="%.2f" y="%.2f" text-anchor="middle">%.2f</text>' % (cx, oy - 6 - 3 * (k % 2), value))
    for value in sorted({item["dy"] for item in hl}):
        cy = oy + value
        s.append('<path class="d" d="M%.3f,%.3fH%.3f"/>' % (ox - 5, cy, ox))
        s.append('<text class="t" x="%.2f" y="%.2f" text-anchor="end">%.2f</text>' % (ox - 6, cy + 0.8, value))
    for item in hl:
        cx, cy = P(item["x"], item["y"])
        s.append('<path d="M%.3f,%.3fV%.3fM%.3f,%.3fH%.3f" stroke="#1f4fd0" stroke-width="0.08" '
                 'stroke-dasharray="0.4,0.6"/>' % (cx, oy, cy, ox, cy, cx))
    s.append('<path d="M%.3f,%.3fl-3,0M%.3f,%.3fl0,-3" stroke="#000" stroke-width="0.3"/>' % (ox, oy, ox, oy))
    s.append('<text x="%.2f" y="%.2f" font-size="2.4">datum (0,0)</text>' % (ox - 14, oy - 8))
    # 100 mm check bars
    by = oy + h + 12
    s.append('<path d="M%.3f,%.3fh%gM%.3f,%.3fv-2M%.3f,%.3fv-2" stroke="#000" stroke-width="0.3"/>'
             % (ox, by, BAR, ox, by, ox + BAR, by))
    s.append('<text x="%.2f" y="%.2f" font-size="2.6">100 mm check bar - measure before use</text>' % (ox + 2, by + 4))
    bx = min(ox + w + 12, pw - MARGIN)
    if oy + BAR <= ph - MARGIN:
        s.append('<path d="M%.3f,%.3fv%gM%.3f,%.3fh2M%.3f,%.3fh2" stroke="#000" stroke-width="0.3"/>'
                 % (bx, oy, BAR, bx, oy, bx, oy + BAR))
        s.append('<text x="%.2f" y="%.2f" font-size="2.6" transform="rotate(90 %.2f %.2f)">100 mm</text>'
                 % (bx + 3, oy + 40, bx + 3, oy + 40))
    pairs = [(a["reference"], c["reference"], round(math.dist((a["x"], a["y"]), (c["x"], c["y"])), 3))
             for a, c in itertools.combinations(hl, 2)]
    note = ("%s outline %.2f x %.2f mm (from the board). Top view, datum = top-left outline corner, mm. "
            "Print at 100 %% and measure the check bars. Review sheet, NOT a drawing release." % (title, w, h)).strip()
    s.append('<text x="%.2f" y="%.2f" font-size="2.8">%s</text>' % (MARGIN, ph - MARGIN + 6, _esc(note)))
    s.append('<text x="%.2f" y="%.2f" font-size="2.4">Hole distances: %s</text>' % (
        MARGIN, ph - MARGIN + 10, _esc("; ".join("%s-%s %.2f" % p for p in pairs))))
    s.append("</svg>")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    svg = output / "mounting_1to1.svg"
    svg.write_text("\n".join(s))
    files = {svg.name: sha256(svg)}
    rsvg = shutil.which("rsvg-convert")
    if rsvg:
        for fmt, name in (("pdf", "mounting_1to1.pdf"), ("png", "mounting_preview.png")):
            r = run([rsvg, "-f", fmt, "-o", output / name] + (["--zoom", "4"] if fmt == "png" else []) + [svg], timeout=120)
            if r["exit_code"]:
                raise KitError("rsvg-convert %s failed: %s" % (fmt, r["stderr"][-300:]), 13)
            files[name] = sha256(output / name)
    return {"status": "SHEET_READY", "created": now(), "board": str(board_path), "board_sha256": sha256(board_path),
            "page": page, "scale": "1:1", "outline_mm": [round(w, 4), round(h, 4)],
            "datum": "outline top-left corner (Edge.Cuts centre lines), mm, y down",
            "holes": [{k: v for k, v in item.items() if k not in ("x", "y")} for item in hl],
            "distances": [{"from": a, "to": c, "mm": d} for a, c, d in pairs],
            "washer_mm": washer, "head_mm": head, "bodies": body_layers, "files": files,
            "pdf": bool(rsvg), "physical_check": "PENDING",
            "limitations": ["Review sheet from the board file; not a drawing release.",
                            "Printer scaling must be confirmed with both 100 mm bars before any fit check.",
                            "Chassis suitability, tool access and cable bend radii need a physical check."]}


def _esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
