"""Copper and placement difference between two board files (read-only).

Compares tracks and arcs (net, layer, width, exact end points), vias (net, position, size, drill, layers),
footprints (position, orientation, side, pad nets), zones (net, layers, outline, priority, rule area,
clearance) and the outline size. Positions are relative to each board's outline top-left corner (Edge.Cuts
centre lines), so a translated board compares equal when its copper moved with it.

With review regions (outline-relative mm boxes), every change must lie inside a region (a track counts as
inside when all its points are inside); anything else is UNEXPECTED. Added tracks shorter than the sliver
length outside every region are reported separately as slivers - autorouter imports write such pieces
from existing track ends to pad centres. A pure count comparison is not evidence that copper is restored;
this lists objects. It does not judge whether a change is electrically right, and it never writes a board.
"""
import collections
import math

from tools.core.common import now
from tools.core.evidence import recorded_run
from tools.quality import board_model as boardmodel

DIGITS = 4  # 0.1 um: well below KiCad's 1 nm grid noise in mm text, far below any manufacturing feature


def _key_points(b):
    x0, y0 = b["outline_bbox"][:2] if b["outline_bbox"] else (0.0, 0.0)

    def k(p):
        return (round(p[0] - x0, DIGITS), round(p[1] - y0, DIGITS))

    copper = {}
    for t in b["tracks"]:
        a, c = sorted([k(t["start"]), k(t["end"])])
        key = (t["kind"], t["net"], t["layer"], round(t["width"], 4), a, c) + ((k(t["mid"]),) if "mid" in t else ())
        copper[key] = {"points": [a, c], "length": math.dist(t["start"], t["end"])}
    for v in b["vias"]:
        key = ("via", v["net"], k(v["at"]), round(v["size"], 4), round(v["drill"], 4), tuple(v["layers"]))
        copper[key] = {"points": [k(v["at"])], "length": 0.0}
    fps = {}
    for ref, f in b["footprints"].items():
        fps[ref] = {"at": k(f["at"]), "angle": round(f["angle"] % 360, 3), "side": f["side"],
                    "pads": sorted((p["number"], p["net"]) for p in f["pads"])}
    zones = {}
    for z in b["zones"]:
        key = (z["name"], z["net"], tuple(z["layers"]))
        zones.setdefault(key, []).append({"outline": [k(p) for p in z["outline"]], "priority": z["priority"],
                                          "rule_area": z["rule_area"], "clearance": z["clearance"]})
    bb = b["outline_bbox"]
    size = (round(bb[2] - bb[0], DIGITS), round(bb[3] - bb[1], DIGITS)) if bb else None
    return copper, fps, zones, size


def _inside(points, regions):
    return any(all(x1 <= x <= x2 and y1 <= y <= y2 for x, y in points) for x1, y1, x2, y2 in regions)


def _short_net(name):
    return name.rsplit("/", 1)[-1] or "<no net>"


def compare(before, after, regions=(), sliver_mm=0.1):
    regions = [(min(r[0], r[2]), min(r[1], r[3]), max(r[0], r[2]), max(r[1], r[3])) for r in regions]
    ca, fa, za, sa = _key_points(boardmodel.load(before))
    cb, fb, zb, sb = _key_points(boardmodel.load(after))
    findings, slivers = [], []
    changes = {"removed": [k for k in ca if k not in cb], "added": [k for k in cb if k not in ca]}
    summary = {}
    for what, keys in changes.items():
        src = ca if what == "removed" else cb
        summary[what] = dict(sorted(collections.Counter("%s %s" % (k[0], _short_net(k[1])) for k in keys).items()))
        for k in keys:
            item = {"change": what, "kind": k[0], "net": k[1], "points": src[k]["points"]}
            if not regions or _inside(src[k]["points"], regions):
                continue
            if what == "added" and k[0] in ("segment", "arc") and src[k]["length"] < sliver_mm:
                slivers.append(dict(item, length_mm=round(src[k]["length"], 4)))
            else:
                findings.append(item)
    footprints = []
    for ref in sorted(set(fa) | set(fb)):
        x, y = fa.get(ref), fb.get(ref)
        if x == y:
            continue
        if x is None or y is None:
            what = "added" if x is None else "removed"
        else:
            what = ", ".join(n for n in ("at", "angle", "side", "pads") if x[n] != y[n]) + " changed"
        entry = {"reference": ref, "change": what, "before": x and x["at"], "after": y and y["at"]}
        footprints.append(entry)
        pts = [p["at"] for p in (x, y) if p]
        if regions and not _inside(pts, regions):
            findings.append({"change": "footprint " + what, "kind": "footprint", "reference": ref, "points": pts})
    zones = []
    for key in sorted(set(za) | set(zb), key=str):
        x, y = za.get(key), zb.get(key)
        if x == y:
            continue
        zones.append({"name": key[0], "net": key[1], "layers": list(key[2]),
                      "change": "added" if x is None else "removed" if y is None else "changed"})
        old = {p for z in x or [] for p in z["outline"]}
        new = {p for z in y or [] for p in z["outline"]}
        moved = sorted(old ^ new)
        settings_changed = x and y and [dict(z, outline=None) for z in x] != [dict(z, outline=None) for z in y]
        if regions and ((moved and not _inside(moved, regions)) or settings_changed):
            findings.append({"change": "zone " + zones[-1]["change"], "kind": "zone", "name": key[0],
                             "net": key[1], "points": moved[:8]})
    if sa != sb and regions:
        findings.append({"change": "outline size %s -> %s" % (sa, sb), "kind": "outline", "points": []})
    status = "NO_CHANGES" if not (changes["removed"] or changes["added"] or footprints or zones or sa != sb) \
        else ("UNEXPECTED_CHANGES" if findings or slivers else "CHANGES_INSIDE_REGIONS") if regions \
        else "CHANGES_LISTED"
    return {"status": status, "created": now(), "before": str(before), "after": str(after),
            "datum": "outline top-left corner (Edge.Cuts centre lines), mm, y down",
            "regions": regions, "sliver_mm": sliver_mm, "outline_size": {"before": sa, "after": sb},
            "copper": {"removed": len(changes["removed"]), "added": len(changes["added"]), "by_kind_net": summary},
            "footprints": footprints, "zones": zones, "unexpected": findings, "slivers": slivers,
            "limitations": ["Lists object differences only; does not judge electrical correctness, refill state "
                            "or DRC.", "Regions are review intent, not proof that changes inside them are right."]}


def run(project, before, after, regions=(), sliver_mm=0.1):
    return recorded_run(project, "board-diff", lambda: compare(before, after, regions, sliver_mm))
