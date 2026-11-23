"""Read-only inventory of a .kicad_pcb for review checks (no pcbnew, no writes).

Coordinates are KiCad file coordinates in mm (y down). Pad and hole positions are absolute: the pad
offset is rotated by the footprint orientation (KiCad stores bottom-side footprints already mirrored).
The outline bounding box uses the Edge.Cuts centre lines, so it is independent of the line width.
"""
from pathlib import Path

from tools.core import sexpr
from tools.core.common import KitError
from tools.thermal.geometry import _chain, _shape_polyline, rotate


def _xy(node, name="at"):
    c = sexpr.child(node, name)
    return (float(c[1]), float(c[2])) if c else (0.0, 0.0)


def _angle(node):
    c = sexpr.child(node, "at")
    return float(c[3]) if c and len(c) > 3 else 0.0


def _net(node):
    c = sexpr.child(node, "net")
    if not c:
        return ""
    names = [v for v in c[1:] if isinstance(v, str)]
    return str(names[-1]) if names else ""   # KiCad 10: (net "NAME"); older: (net 3 "NAME")


def _layers(node):
    c = sexpr.child(node, "layers")
    out = [str(v) for v in c[1:]] if c else []
    if sexpr.value(node, "layer"):
        out.append(str(sexpr.value(node, "layer")))
    return tuple(out)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _drill(pad):
    """Finished hole diameter of a pad (smallest dimension of a slot), 0 if none."""
    d = sexpr.child(pad, "drill")
    if d is None:
        return 0.0
    nums = [n for n in (_num(v) for v in d[1:] if not isinstance(v, list)) if n is not None]
    return min(nums) if nums else 0.0


def load(path):
    path = Path(path)
    try:
        tree = sexpr.load(path)
    except (OSError, sexpr.ParseError) as exc:
        raise KitError("Cannot read board %s: %s" % (path, exc), 13)
    closed, open_parts = [], []
    for node in tree[1:]:
        if isinstance(node, list) and node and str(node[0]).startswith("gr_") and \
                sexpr.value(node, "layer") == "Edge.Cuts":
            pts, is_closed = _shape_polyline(node)
            if pts:
                (closed if is_closed else open_parts).append(pts)
    loops = closed + (_chain(open_parts) if open_parts else [])
    pts = [p for loop in loops for p in loop]
    bbox = (min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts),
            max(p[1] for p in pts)) if pts else None

    setup = sexpr.child(tree, "setup") or []
    aux = sexpr.child(setup, "aux_axis_origin")
    layers = sexpr.child(tree, "layers") or []
    copper = [str(l[1]) for l in layers[1:] if isinstance(l, list) and len(l) > 1 and str(l[1]).endswith(".Cu")]

    tracks, vias, footprints, zones = [], [], {}, []
    for node in tree[1:]:
        if not isinstance(node, list) or not node:
            continue
        kind = node[0]
        if kind in ("segment", "arc"):
            t = {"kind": kind, "layer": str(sexpr.value(node, "layer")), "net": _net(node),
                 "width": float(sexpr.value(node, "width", 0)), "start": _xy(node, "start"), "end": _xy(node, "end")}
            if kind == "arc":
                t["mid"] = _xy(node, "mid")
            tracks.append(t)
        elif kind == "via":
            vias.append({"at": _xy(node), "size": float(sexpr.value(node, "size", 0)),
                         "drill": float(sexpr.value(node, "drill", 0)), "layers": _layers(node), "net": _net(node)})
        elif kind == "footprint":
            ref = sexpr.properties(node).get("Reference", "?")
            fx, fy = _xy(node)
            fa = _angle(node)
            attr = sexpr.child(node, "attr")
            attrs = {str(v) for v in attr[1:]} if attr else set()
            pads = []
            for pad in sexpr.children(node, "pad"):
                lx, ly = _xy(pad)
                dx, dy = rotate(lx, ly, fa)
                drill = sexpr.child(pad, "drill")
                pads.append({"number": str(pad[1]), "type": str(pad[2]), "net": _net(pad),
                             "x": fx + dx, "y": fy + dy, "drill": _drill(pad),
                             "slot": bool(drill) and "oval" in [str(v) for v in drill[1:] if not isinstance(v, list)]})
            footprints[ref] = {"reference": ref, "footprint": str(node[1]), "at": (fx, fy), "angle": fa,
                               "side": "bottom" if sexpr.value(node, "layer") == "B.Cu" else "top",
                               "attrs": attrs, "dnp": "dnp" in attrs,
                               "exclude_from_bom": "exclude_from_bom" in attrs,
                               "exclude_from_pos": "exclude_from_pos_files" in attrs, "pads": pads}
        elif kind == "zone":
            poly = sexpr.child(node, "polygon")
            outline = [(float(p[1]), float(p[2])) for p in sexpr.children(sexpr.child(poly, "pts") or [], "xy")] \
                if poly else []
            connect = sexpr.child(node, "connect_pads") or []
            zones.append({"name": str(sexpr.value(node, "name", "")), "net": _net(node), "layers": _layers(node),
                          "priority": int(float(sexpr.value(node, "priority", 0))),
                          "rule_area": sexpr.child(node, "keepout") is not None,
                          "clearance": float(sexpr.value(connect, "clearance", 0) or 0), "outline": outline})
    return {"path": str(path), "outline_loops": loops, "outline_bbox": bbox, "copper_layers": copper,
            "aux_origin": (float(aux[1]), float(aux[2])) if aux else (0.0, 0.0),
            "tracks": tracks, "vias": vias, "footprints": footprints, "zones": zones}


def holes(board, slots=False):
    """Every round drilled hole: (plating 'P'/'N', diameter, x, y, owner). Vias are plated.
    With slots=True only the oblong (slot) pad holes are returned instead."""
    out = []
    for ref, fp in board["footprints"].items():
        for p in fp["pads"]:
            if p["type"] in ("thru_hole", "np_thru_hole") and p["drill"] > 0 and p.get("slot", False) == slots:
                out.append(("N" if p["type"] == "np_thru_hole" else "P", p["drill"], p["x"], p["y"],
                            "%s.%s" % (ref, p["number"])))
    for v in board["vias"] if not slots else []:
        if v["drill"] > 0:
            out.append(("P", v["drill"], v["at"][0], v["at"][1], "via"))
    return out
