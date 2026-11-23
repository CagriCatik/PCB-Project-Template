"""Geometry cross-check of an exported fabrication package against the board (read-only).

`scripts/kit export` already checks names and designators (BOM/position/schematic reference sets, DNP
state, drill file names). This check compares *values* with the board:

- positions.csv: side, rotation and X/Y of every placed SMD part (Y up, origin = page origin as written by
  `kicad-cli pcb export pos` without --use-drill-file-origin, or the aux origin with origin="aux");
  DNP / excluded parts absent; through-hole-only parts listed are reported as information.
- Drill files: absolute metric decimal Excellon; no MixedPlating file; every board hole (pads and vias)
  appears exactly once with its diameter and position in the file of its plating, and nothing else.
  No rounding: the tolerance is half a unit of the last decimal place the files actually use.
- Optional fabricator limits (only when given; no fabricator defaults are assumed): minimum via drill,
  minimum NPTH and component hole diameter.
- Gerber job file: copper layer count against the board; thickness and stack-up reported.
- BOM: MPN/manufacturer gaps reported as warnings (the verify `bom` gate owns the policy).
"""
import csv
import json
from pathlib import Path
import re

from tools.core.common import KitError, now
from tools.core.evidence import recorded_run
from tools.quality import board_model as boardmodel


def expand_refs(text, delimiter=","):
    """'R1,R3-R5' -> ['R1', 'R3', 'R4', 'R5'] (same rule as the exporter; quality may not import release)."""
    refs = []
    for part in (p.strip() for p in text.split(delimiter)):
        m = re.fullmatch(r"([A-Za-z_#]+)(\d+)-\1?(\d+)", part)
        if m:
            refs += ["%s%d" % (m.group(1), n) for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        elif part:
            refs.append(part)
    return refs


def _read_csv(path):
    if not path.is_file():
        raise KitError("Package file missing: %s" % path, 13)
    with path.open(newline="") as fp:
        return list(csv.DictReader(fp))


def _positions(b, pkg, origin, errors, info):
    ox, oy = b["aux_origin"] if origin == "aux" else (0.0, 0.0)
    rows = {}
    for row in _read_csv(pkg / "assembly/positions.csv"):
        if row["Ref"] in rows:
            errors.append({"area": "positions", "problem": "listed twice", "reference": row["Ref"]})
        rows[row["Ref"]] = row
    worst = 0.0
    for ref, f in b["footprints"].items():
        smd = any(p["type"] == "smd" for p in f["pads"])
        tht = any(p["type"] == "thru_hole" for p in f["pads"])
        listed = ref in rows
        if f["exclude_from_pos"] or f["dnp"]:
            if listed:
                errors.append({"area": "positions", "problem": "listed although DNP/excluded", "reference": ref})
            continue
        if smd and not listed:
            errors.append({"area": "positions", "problem": "SMD part missing", "reference": ref})
        if not listed:
            continue
        if tht and not smd:
            info.append("through-hole-only part %s listed in positions.csv" % ref)
        row = rows[ref]
        if row["Side"] != f["side"]:
            errors.append({"area": "positions", "problem": "side %s, board %s" % (row["Side"], f["side"]),
                           "reference": ref})
        x, y = f["at"][0] - ox, -(f["at"][1] - oy)
        d = max(abs(float(row["PosX"]) - x), abs(float(row["PosY"]) - y))
        worst = max(worst, d)
        if d > 0.001:
            errors.append({"area": "positions", "problem": "position differs by %.4f mm" % d, "reference": ref})
        if abs((float(row["Rot"]) - f["angle"] + 180) % 360 - 180) > 0.01:
            errors.append({"area": "positions", "problem": "rotation %s, board %.3f" % (row["Rot"], f["angle"]),
                           "reference": ref})
    for ref in rows:
        if ref not in b["footprints"]:
            errors.append({"area": "positions", "problem": "not on the board", "reference": ref})
    return {"parts": len(rows), "top": sum(r["Side"] == "top" for r in rows.values()),
            "bottom": sum(r["Side"] == "bottom" for r in rows.values()), "max_position_difference_mm": worst,
            "origin": "aux origin %s" % (b["aux_origin"],) if origin == "aux" else "page origin"}


def parse_excellon(path):
    text = Path(path).read_text(errors="replace")
    problems = []
    if not re.search(r"^METRIC", text, re.M) or "FORMAT={-:-/ absolute / metric / decimal}" not in text:
        problems.append("not absolute metric decimal Excellon; comparison not valid")
    func = re.search(r"TF\.FileFunction,([^\n]*)", text)
    func = func.group(1) if func else ""
    if "MixedPlating" in func:
        problems.append("merged PTH/NPTH file (plating only in comment attributes)")
    default = "NonPlated" if "NonPlated" in func else "Plated"
    tools, attr, cur, hits, decimals, slots = {}, default, None, [], 0, 0
    for line in text.splitlines():
        if "G85" in line:
            slots += 1
            continue
        if line.startswith("; #@! TA.AperFunction"):
            attr = line.strip().split(",", 1)[1]
            continue
        m = re.match(r"^T(\d+)C([\d.]+)", line)
        if m:
            tools[int(m.group(1))] = (float(m.group(2)), attr)
            continue
        m = re.match(r"^T(\d+)$", line)
        if m:
            cur = int(m.group(1))
            continue
        m = re.match(r"^X([-\d.]+)Y([-\d.]+)$", line)
        if m:
            if cur not in tools:
                problems.append("hit without a selected tool")
                continue
            decimals = max([decimals] + [len(c.split(".")[1]) if "." in c else 0 for c in m.groups()])
            d, a = tools[cur]
            hits.append(("N" if "NonPlated" in a else "P", d, float(m.group(1)), float(m.group(2)), a))
    return {"file": Path(path).name, "function": func, "problems": problems, "hits": hits,
            "tools": sorted(set((d, a) for d, a in tools.values())), "decimals": decimals, "slots": slots}


def _drills(b, pkg, limits, errors, warnings, info):
    files = sorted((pkg / "fabrication/drill").glob("*.drl"))
    if not files:
        errors.append({"area": "drill", "problem": "no Excellon files"})
        return {}
    parsed = [parse_excellon(f) for f in files]
    for p in parsed:
        for problem in p["problems"]:
            errors.append({"area": "drill", "problem": problem, "file": p["file"]})
    decimals = max(p["decimals"] for p in parsed)
    tol = 0.5 * 10 ** -decimals + 1e-9
    want = [(k, d, x, -y, owner) for k, d, x, y, owner in boardmodel.holes(b)]
    sets = {}
    for k, name in (("P", "PTH"), ("N", "NPTH")):
        got = sorted((d, x, y) for p in parsed for kk, d, x, y, _ in p["hits"] if kk == k)
        left, missing = list(got), []
        for _, d, x, y, owner in sorted(h for h in want if h[0] == k):
            j = next((i for i, (gd, gx, gy) in enumerate(left)
                      if abs(gd - d) <= tol and abs(gx - x) <= tol and abs(gy - y) <= tol), None)
            if j is None:
                missing.append({"owner": owner, "diameter": d, "x": round(x, 4), "y": round(y, 4)})
            else:
                left.pop(j)
        if missing or left:
            errors.append({"area": "drill", "problem": "%s set differs from the board" % name,
                           "missing": missing[:10], "extra": [list(e) for e in left[:10]],
                           "missing_count": len(missing), "extra_count": len(left)})
        per = {}
        for d, _, _ in got:
            per["%g" % d] = per.get("%g" % d, 0) + 1
        sets[name] = {"hits": len(got), "board_holes": sum(1 for h in want if h[0] == k),
                      "equal": not missing and not left, "per_diameter": per}
    for p in parsed:
        for d, a in p["tools"]:
            plating = "N" if "NonPlated" in a else "P"
            if plating == "N" and limits.get("min_npth_mm") and d < limits["min_npth_mm"]:
                errors.append({"area": "drill", "problem": "NPTH %.3f mm below limit %.3f mm" % (d, limits["min_npth_mm"])})
            elif "ViaDrill" in a and limits.get("min_via_drill_mm") and d < limits["min_via_drill_mm"]:
                errors.append({"area": "drill", "problem": "via %.3f mm below limit %.3f mm" % (d, limits["min_via_drill_mm"])})
            elif plating == "P" and "ComponentDrill" in a and limits.get("min_component_hole_mm") \
                    and d < limits["min_component_hole_mm"]:
                users = sorted({o.split(".")[0] for k, dd, _, _, o in want if k == "P" and o != "via"
                                and abs(dd - d) < 0.0005})
                warnings.append("component hole %.3f mm below %.3f mm in %s" % (d, limits["min_component_hole_mm"], users))
    board_slots = boardmodel.holes(b, slots=True)
    file_slots = sum(p["slots"] for p in parsed)
    if board_slots or file_slots:
        warnings.append("slots not compared (board %d oblong holes, files %d G85 slots): review them in the "
                        "fabricator preview" % (len(board_slots), file_slots))
    info.append("drill files: %s; resolution %g mm, tolerance %.4f mm" % (
        ", ".join(p["file"] for p in parsed), 10 ** -decimals, tol))
    return {"files": [p["file"] for p in parsed], "tolerance_mm": tol, "sets": sets,
            "slots": {"board": len(board_slots), "files": file_slots, "compared": False}}


def _job(b, pkg, errors):
    jobs = sorted((pkg / "fabrication/gerbers").glob("*.gbrjob"))
    if not jobs:
        errors.append({"area": "job", "problem": "no Gerber job file"})
        return {}
    job = json.loads(jobs[0].read_text())
    spec = job.get("GeneralSpecs", {})
    if spec.get("LayerNumber") != len(b["copper_layers"]):
        errors.append({"area": "job", "problem": "layer count %s, board %d" % (spec.get("LayerNumber"),
                                                                             len(b["copper_layers"]))})
    return {"file": jobs[0].name, "layers": spec.get("LayerNumber"), "thickness_mm": spec.get("BoardThickness"),
            "stackup": ["%s %s" % (s.get("Type"), s.get("Thickness")) for s in job.get("MaterialStackup", [])
                        if s.get("Type") in ("Copper", "Dielectric")]}


def _bom(b, pkg, warnings):
    rows = _read_csv(pkg / "assembly/bom.csv")
    gaps = sorted(r for row in rows for r in expand_refs(row.get("Refs", ""))
                  if not (row.get("MPN", "").strip() and row.get("Manufacturer", "").strip()))
    if gaps:
        warnings.append("BOM without MPN/manufacturer: %s" % ", ".join(gaps))
    return {"lines": len(rows), "without_mpn": len(gaps)}


def check(board_path, package, origin="page", limits=None):
    b = boardmodel.load(board_path)
    pkg = Path(package)
    if not pkg.is_dir():
        raise KitError("Package directory not found: %s" % pkg, 13)
    limits = {k: v for k, v in (limits or {}).items() if v}
    errors, warnings, info = [], [], []
    result = {"positions": _positions(b, pkg, origin, errors, info),
              "drill": _drills(b, pkg, limits, errors, warnings, info),
              "job": _job(b, pkg, errors), "bom": _bom(b, pkg, warnings)}
    return dict(result, status="FAIL" if errors else "PASS", created=now(), board=str(board_path),
                package=str(pkg), limits=limits, errors=errors, warnings=warnings, info=info,
                limitations=["Compares exported values with the board file; it does not inspect Gerber copper "
                             "or replace the fabricator's CAM preview.",
                             "Fabricator limits are checked only when given; none are assumed."])


def run(project, board_path, package, origin="page", limits=None):
    return recorded_run(project, "fab-check", lambda: check(board_path, package, origin, limits))
