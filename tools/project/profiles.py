"""Board profiles: example stack-up, design-rule minimums and net classes.

Profile definitions live in meta/templates/profiles/<id>.json. Their native
defaults (default.kicad_pro / default.kicad_pcb) are authored by KiCad's own
pcbnew and committed under hardware/native-defaults/profiles/<id>/, so project
creation needs no KiCad installation. Only the stack-up block is inserted as
text (pcbnew's Python bindings do not expose BOARD_STACKUP in KiCad 10.0.7);
the result is re-loaded by pcbnew to prove KiCad parses it.
"""

import json
from pathlib import Path
import shutil
import tempfile

from tools.core import kicad_env
from tools.core.common import KitError, run

ROOT = kicad_env.KIT_ROOT
PROFILE_DIR = ROOT / "meta/templates/profiles"
DEFAULTS_DIR = ROOT / "hardware/native-defaults/profiles"
DEFAULT_PROFILE = "2-layer"


def profiles():
    found = {}
    for path in sorted(PROFILE_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        _validate(data, path)
        found[data["id"]] = data
    return found


def get_profile(profile_id):
    found = profiles()
    if profile_id not in found:
        raise KitError("Unknown board profile %r; choose one of: %s" % (profile_id, ", ".join(found)))
    return found[profile_id]


def _validate(data, path):
    coppers = [l["layer"] for l in data.get("stackup", []) if l.get("type") == "copper"]
    if len(coppers) != data.get("copper_layers"):
        raise KitError("%s: copper_layers=%s but stack-up lists %d copper layers" % (path.name,
                                                                                    data.get("copper_layers"), len(coppers)))
    if not data.get("netclasses") or data["netclasses"][0]["name"] != "Default":
        raise KitError("%s: the first net class must be 'Default'" % path.name)
    for key, value in data.get("rules", {}).items():
        if not isinstance(value, (int, float)) or value <= 0:
            raise KitError("%s: rule %s must be a positive number" % (path.name, key))


def board_thickness(profile):
    return round(sum(l["thickness"] for l in profile["stackup"]), 4)


def stackup_block(profile):
    """KiCad 10 `(stackup ...)` text, same structure pcbnew writes."""
    order = ["F.SilkS", "F.Paste"] + [l["layer"] for l in profile["stackup"]] + ["B.Paste", "B.SilkS"]
    entries = {l["layer"]: l for l in profile["stackup"]}
    extra = {"F.SilkS": "Top Silk Screen", "F.Paste": "Top Solder Paste", "B.Paste": "Bottom Solder Paste",
             "B.SilkS": "Bottom Silk Screen"}
    lines = ["\t\t(stackup"]
    for name in order:
        item = entries.get(name, {"type": extra.get(name)})
        lines.append('\t\t\t(layer "%s"' % name)
        lines.append('\t\t\t\t(type "%s")' % item["type"])
        if "Mask" in name:
            lines.append('\t\t\t\t(color "Green")')
        if "thickness" in item:
            lines.append("\t\t\t\t(thickness %s)" % item["thickness"])
        for key in ("material", "epsilon_r", "loss_tangent"):
            if key in item:
                value = '"%s"' % item[key] if isinstance(item[key], str) else item[key]
                lines.append("\t\t\t\t(%s %s)" % (key, value))
        lines.append("\t\t\t)")
    lines += ['\t\t\t(copper_finish "None")', "\t\t\t(dielectric_constraints no)", "\t\t)"]
    return "\n".join(lines) + "\n"


_AUTHOR = r"""
import json, sys, pcbnew
spec = json.loads(sys.argv[2])
b = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.FromMM
b.SetCopperLayerCount(spec["copper_layers"])
ds = b.GetDesignSettings()
r = spec["rules"]
ds.m_MinClearance = mm(r["min_clearance"])
ds.m_TrackMinWidth = mm(r["min_track_width"])
ds.m_ViasMinSize = mm(r["min_via_diameter"])
ds.m_MinThroughDrill = mm(r["min_through_hole_diameter"])
ds.m_ViasMinAnnularWidth = mm(r["min_via_annular_width"])
ds.m_HoleToHoleMin = mm(r["min_hole_to_hole"])
ds.m_CopperEdgeClearance = mm(r["min_copper_edge_clearance"])
ds.SetBoardThickness(mm(spec["thickness"]))
ns = ds.m_NetSettings
for c in spec["netclasses"]:
    nc = ns.GetDefaultNetclass() if c["name"] == "Default" else pcbnew.NETCLASS(c["name"])
    nc.SetClearance(mm(c["clearance"])); nc.SetTrackWidth(mm(c["track_width"]))
    nc.SetViaDiameter(mm(c["via_diameter"])); nc.SetViaDrill(mm(c["via_drill"]))
    if c["name"] != "Default":
        ns.SetNetclass(c["name"], nc)
tb = b.GetTitleBlock()
tb.SetTitle("${PROJECTNAME}")
tb.SetRevision("A")
assert pcbnew.SaveBoard(sys.argv[1], b)
"""

_CHECK = r"""
import json, sys, pcbnew
b = pcbnew.LoadBoard(sys.argv[1])
ds = b.GetDesignSettings()
ns = ds.m_NetSettings
print(json.dumps({
    "copper_layers": b.GetCopperLayerCount(),
    "thickness": pcbnew.ToMM(ds.GetBoardThickness()),
    "has_stackup": bool(ds.m_HasStackup),
    "min_track_width": pcbnew.ToMM(ds.m_TrackMinWidth),
    "min_clearance": pcbnew.ToMM(ds.m_MinClearance),
    "netclasses": sorted(str(k) for k in ns.GetNetclasses().keys()) + ["Default"],
    "default_track_width": pcbnew.ToMM(ns.GetDefaultNetclass().GetTrackWidth()),
    "title": b.GetTitleBlock().GetTitle(),
}))
"""


def _python():
    python = kicad_env.bundled_python()
    if not python:
        raise KitError("Building profile defaults needs KiCad %s with its bundled Python." % kicad_env.KICAD_VERSION, 10)
    return python


def inspect(board):
    """What KiCad's pcbnew reads back from a board file (proves KiCad parses it)."""
    record = run([_python(), "-c", _CHECK, board], timeout=120)
    try:
        return json.loads(record["stdout"].strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise KitError("pcbnew could not load %s: %s" % (board, record["stderr"][-1500:]), 13)


def build(profile_id, out_dir):
    """Author default.kicad_pro/.kicad_pcb for one profile with pcbnew; returns the read-back."""
    profile = get_profile(profile_id)
    out_dir = Path(out_dir)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp)
        blank = ROOT / "hardware/native-defaults"
        for ext in ("kicad_pro", "kicad_pcb"):
            shutil.copy2(blank / ("default." + ext), stage / ("default." + ext))
        spec = dict(profile, thickness=board_thickness(profile))
        record = run([_python(), "-c", _AUTHOR, stage / "default.kicad_pcb", json.dumps(spec)], timeout=120)
        if record["exit_code"]:
            raise KitError("pcbnew failed to author profile %s: %s" % (profile_id, record["stderr"][-1500:]))
        pcb = stage / "default.kicad_pcb"
        text = pcb.read_text()
        marker = "\t(setup\n"
        if marker not in text or "(stackup" in text:
            raise KitError("Unexpected board layout from pcbnew while adding the stack-up.")
        pcb.write_text(text.replace(marker, marker + stackup_block(profile), 1))
        readback = inspect(pcb)
        expected = {"copper_layers": profile["copper_layers"], "has_stackup": True,
                    "min_track_width": profile["rules"]["min_track_width"]}
        wrong = {k: readback.get(k) for k, v in expected.items() if readback.get(k) != v}
        if wrong or abs(readback["thickness"] - spec["thickness"]) > 1e-6:
            raise KitError("pcbnew read back unexpected values for %s: %s" % (profile_id, wrong or readback))
        out_dir.mkdir(parents=True, exist_ok=True)
        for ext in ("kicad_pro", "kicad_pcb"):
            shutil.copy2(stage / ("default." + ext), out_dir / ("default." + ext))
    return readback


def default_files(profile_id):
    get_profile(profile_id)
    folder = DEFAULTS_DIR / profile_id
    files = [folder / "default.kicad_pro", folder / "default.kicad_pcb"]
    if not all(f.is_file() for f in files):
        raise KitError("Native defaults for profile %s are missing; run scripts/kit templates rebuild-profiles."
                       % profile_id)
    return files
