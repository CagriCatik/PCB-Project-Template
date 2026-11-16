"""Conservative drawing hints, not a substitute for inspecting rendered sheets.

Only visible text anchors are checked: font metrics, pin names, symbol bodies,
mirroring and custom drawing-sheet/title-block geometry are deliberately not
approximated as authoritative collision boxes.
"""
from pathlib import Path
from tools.core import sexpr as sx
from tools.schematic.model import inventory

PAPERS = {"A5": (210, 148), "A4": (297, 210), "A3": (420, 297),
          "A2": (594, 420), "A1": (841, 594), "A0": (1189, 841)}


def hints(schematic):
    schematic = Path(schematic).resolve()
    native, _ = inventory(schematic)
    findings = []
    for item in native["sheets"]:
        tree = sx.load(schematic.parent / item["file"])
        paper = sx.child(tree, "paper")
        size = PAPERS.get(str(paper[1])) if paper and len(paper) > 1 else None
        if size and "portrait" in paper:
            size = size[::-1]
        anchors = []
        nodes = []
        for symbol in sx.children(tree, "symbol"):
            ref = sx.properties(symbol).get("Reference", "?")
            nodes.extend((ref + ":" + str(p[1]), p, str(p[2])) for p in sx.children(symbol, "property"))
        for kind in ("text", "label", "global_label", "hierarchical_label"):
            nodes.extend((kind, n, str(n[1])) for n in sx.children(tree, kind))
        for owner, node, text in nodes:
            effects = sx.child(node, "effects")
            if sx.flag(effects or [], "hide") or "hide" in (effects or []):
                continue
            at = sx.child(node, "at")
            if not at or len(at) < 3:
                continue
            x, y = float(at[1]), float(at[2])
            if size and not (0 <= x <= size[0] and 0 <= y <= size[1]):
                findings.append({"sheet": item["file"], "kind": "text_anchor_outside_paper",
                                 "owner": owner, "text": text, "at_mm": [x, y]})
            for other, ox, oy in anchors:
                if abs(x - ox) < .25 and abs(y - oy) < .25:
                    findings.append({"sheet": item["file"], "kind": "text_anchors_coincide",
                                     "owners": [other, owner], "at_mm": [x, y]})
            anchors.append((owner, x, y))
        if not sx.children(tree, "text") and not sx.children(tree, "text_box"):
            findings.append({"sheet": item["file"], "kind": "no_functional_annotations"})
    return {"status": "HINTS_ONLY", "findings": findings,
            "limitations": "Checks text anchors only; inspect all overviews and details for actual collisions, grouping, flow and title-block clearance."}
