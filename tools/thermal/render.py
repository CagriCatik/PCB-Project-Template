"""Heatmap PNGs (stdlib zlib writer) and the self-contained HTML report."""

import base64
import html
import struct
import zlib

from tools.thermal.geometry import _np

# Perceptually ordered dark-to-bright ramp (approximation of "inferno").
_RAMP = [(0.0, (0, 0, 4)), (0.25, (87, 16, 110)), (0.5, (188, 55, 84)), (0.75, (249, 142, 9)),
         (1.0, (252, 255, 164))]


def colorize(values):
    np = _np()
    v = np.clip(values, 0, 1)
    out = np.zeros(v.shape + (3,))
    for (p0, c0), (p1, c1) in zip(_RAMP, _RAMP[1:]):
        sel = (v >= p0) & (v <= p1)
        t = ((v - p0) / (p1 - p0))[sel][:, None]
        out[sel] = np.array(c0) * (1 - t) + np.array(c1) * t
    return out.astype(np.uint8)


def write_png(path, rgba):
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    with open(path, "wb") as fp:
        fp.write(png)


def heatmap(path, field, mask, t_min, t_max, grid, footprints=(), hotspots=(), target_px=900):
    """Board viewed from the top (bottom layer not mirrored); outside the outline transparent."""
    np = _np()
    scale = max(1, int(target_px / max(field.shape[1], 1)))
    norm = (np.nan_to_num(field, nan=t_min) - t_min) / max(t_max - t_min, 1e-9)
    rgb = colorize(norm)
    alpha = np.where(mask, 255, 0).astype(np.uint8)[..., None]
    img = np.concatenate([rgb, alpha], axis=2).repeat(scale, axis=0).repeat(scale, axis=1)

    def px(x, y):
        return int((y - grid.y0) / grid.cell * scale), int((x - grid.x0) / grid.cell * scale)

    for fp in footprints:  # component extents as thin white boxes
        pts = [(p["x"], p["y"]) for p in fp["pads"]] or [(fp["x"], fp["y"])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        (r0, c0), (r1, c1) = px(min(xs) - 0.5, min(ys) - 0.5), px(max(xs) + 0.5, max(ys) + 0.5)
        r0, r1 = sorted((max(r0, 0), min(r1, img.shape[0] - 1)))
        c0, c1 = sorted((max(c0, 0), min(c1, img.shape[1] - 1)))
        img[r0, c0:c1 + 1] = img[r1, c0:c1 + 1] = img[r0:r1 + 1, c0] = img[r0:r1 + 1, c1] = (255, 255, 255, 200)
    for spot in hotspots:  # cyan crosses
        r, c = px(spot["x_mm"], spot["y_mm"])
        for d in range(-2 * scale, 2 * scale + 1):
            if 0 <= r + d < img.shape[0] and 0 <= c < img.shape[1]:
                img[r + d, c] = (0, 255, 255, 255)
            if 0 <= r < img.shape[0] and 0 <= c + d < img.shape[1]:
                img[r, c + d] = (0, 255, 255, 255)
    write_png(path, img)


def colorbar(path, width=400, height=16):
    np = _np()
    rgb = colorize(np.tile(np.linspace(0, 1, width), (height, 1)))
    write_png(path, np.concatenate([rgb, np.full((height, width, 1), 255, np.uint8)], axis=2))


def _img(path):
    return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()


def _table(rows, columns):
    head = "".join("<th>%s</th>" % html.escape(c) for c in columns)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % html.escape(_fmt(r.get(c))) for c in columns)
                   for r in rows)
    return "<table><tr>%s</tr>%s</table>" % (head, body or "<tr><td colspan=99>none</td></tr>")


def _fmt(v):
    if isinstance(v, float):
        return "%.2f" % v
    return "" if v is None else str(v)


def report(path, result, out_dir):
    s = result["summary"]
    status_color = {"PASS": "#1f7a1f", "FAIL": "#b00020"}.get(result["status"], "#555")
    assumptions = [{"parameter": k, "value": v["value"], "source": v["source"], "note": v.get("note", "")}
                   for k, v in result["assumptions"].items()]
    page = """<!DOCTYPE html><html><head><meta charset="utf-8"><title>Thermal estimate – {name}</title>
<style>body{{font-family:-apple-system,Helvetica,Arial,sans-serif;margin:24px;max-width:1100px;color:#222}}
table{{border-collapse:collapse;margin:8px 0 20px}}td,th{{border:1px solid #ccc;padding:4px 8px;font-size:13px;text-align:left}}
th{{background:#f2f2f2}}.banner{{background:#fff4ce;border:1px solid #e0b800;padding:10px;margin-bottom:16px}}
.status{{color:#fff;background:{color};padding:2px 10px;border-radius:4px}}img{{max-width:100%;background:#ddd}}
.bar{{display:flex;align-items:center;gap:8px}}</style></head><body>
<h1>Thermal estimate: {name} <span class="status">{status}</span></h1>
<div class="banner"><b>ESTIMATE – not a measurement.</b> Steady-state 2.5D model (two outer copper layers,
laminate, vias, convection). Component values are board temperatures under the part unless θ<sub>JB</sub>
is given. Validate with thermocouple or IR measurements on a prototype before relying on these numbers.</div>
<p>Board: {board}<br>Ambient {amb:.1f} °C · grid {grid} mm · {unknowns} unknowns · total power {pin:.3f} W ·
energy balance {pout:.3f} W out (residual {res:.2e} W)</p>
<p>Max top {tmax_top:.1f} °C · max bottom {tmax_bot:.1f} °C · limit {limit:.1f} °C</p>
<h2>Top layer (F.Cu side)</h2><img src="{top}">
<h2>Bottom layer (B.Cu side, viewed from top, not mirrored)</h2><img src="{bot}">
<div class="bar">{tmin:.1f} °C <img src="{bar}" style="width:400px;height:16px"> {tmaxall:.1f} °C</div>
<h2>Components</h2>{components}
<h2>Hotspots</h2>{hotspots}
<h2>Findings</h2><ul>{findings}</ul>
<h2>Warnings and limitations</h2><ul>{warnings}</ul>
<h2>Assumptions</h2>{assumptions}
</body></html>""".format(
        name=html.escape(result["project"]), status=result["status"], color=status_color,
        board=html.escape(result["board"]), amb=s["ambient_c"], grid=s["grid_mm"], unknowns=s["unknowns"],
        pin=s["power_in_w"], pout=s["power_out_w"], res=s["residual_w"], tmax_top=s["max_top_c"],
        tmax_bot=s["max_bottom_c"], limit=s["board_max_c"], tmin=s["scale_min_c"], tmaxall=s["scale_max_c"],
        top=_img(out_dir / "temperature_top.png"), bot=_img(out_dir / "temperature_bottom.png"),
        bar=_img(out_dir / "colorbar.png"),
        components=_table(result["components"], ["reference", "side", "power_w", "basis", "heat_entry",
                                                 "board_max_c", "board_mean_c", "junction_estimate_c", "limit_c",
                                                 "status"]),
        hotspots=_table(result["hotspots"], ["rank", "layer", "x_mm", "y_mm", "temperature_c", "nearest"]),
        findings="".join("<li>%s</li>" % html.escape(f) for f in result["findings"]) or "<li>none</li>",
        warnings="".join("<li>%s</li>" % html.escape(w) for w in result["warnings"]),
        assumptions=_table(assumptions, ["parameter", "value", "source", "note"]))
    path.write_text(page, encoding="utf-8")
