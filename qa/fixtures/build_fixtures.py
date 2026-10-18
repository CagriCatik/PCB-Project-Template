#!/usr/bin/env python3
"""Regenerate the native KiCad 10.0.7 reference projects under qa/fixtures/.

Both are *tooling* references built only from KiCad's official libraries, so
that ERC, DRC with schematic parity, library checks, exports, plugins and
relocation can be exercised on genuine KiCad content. Neither is a reviewed
circuit; see qa/fixtures/README.md for purpose and validation status.

- divider:    connector + two resistors, official libraries via global tables.
- custom-lib: two test points from a *project-local* symbol and footprint
              library (copied from the official libraries, attribution kept)
              plus one resistor; libraries referenced via ${KIPRJMOD}.

Schematics are assembled from symbols copied verbatim from the libraries;
boards are built by KiCad's own pcbnew API.
Usage: python3 qa/fixtures/build_fixtures.py [--only NAME] [--output-root DIR]
"""

import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.core import kicad_env  # noqa: E402

# Fixed namespace keeps regenerated UUIDs stable, so fixture diffs stay reviewable.
NS = uuid.UUID("6f1d6f0e-5c11-4e43-9a52-6b2b1f6c9a01")
SYM_LIB = "hardware/libraries/symbols/Project_Symbols.kicad_sym"
FP_LIB = "hardware/libraries/footprints/Project_Footprints.pretty"

PROJECTS = {
    "divider": {
        "title": "Kit tooling fixture (not a reviewed circuit)",
        # reference, lib_id, value, footprint lib_id, schematic position, pin -> net
        "parts": [
            ("J1", "Connector_Generic:Conn_01x03", "Conn_01x03",
             "Connector_PinHeader_2.54mm:PinHeader_1x03_P2.54mm_Vertical", (101.6, 76.2),
             {"1": "VIN", "2": "VOUT", "3": "GND"}),
            ("R1", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", (127.0, 76.2), {"1": "VIN", "2": "VOUT"}),
            ("R2", "Device:R", "10k", "Resistor_SMD:R_0805_2012Metric", (139.7, 76.2), {"1": "VOUT", "2": "GND"}),
        ],
        "placement": {"J1": (110.0, 100.0), "R1": (120.0, 100.0), "R2": (120.0, 105.08)},
        # Track polylines; a point is "REF.PAD", or [x, y] where each may be a number or "REF.PAD".
        "tracks": [
            ("VIN", ["J1.1", "R1.1"]),
            ("VOUT", ["J1.2", ["R2.1", "J1.2"], [122.5, "J1.2"], [122.5, "R1.2"], "R1.2"]),
            ("VOUT", [["R2.1", "J1.2"], "R2.1"]),
            ("GND", ["R2.2", ["R2.2", 107.5], ["J1.3", 107.5], "J1.3"]),
        ],
        "outline": ((105, 95), (128, 112)),
        "local_libraries": False,
    },
    "custom-lib": {
        "title": "Portable custom-library reference (not a reviewed circuit)",
        "parts": [
            ("TP1", "Project_Symbols:TestPoint", "TP_A", "Project_Footprints:TestPoint_Pad_D1.5mm", (101.6, 76.2),
             {"1": "A"}),
            ("R1", "Device:R", "1k", "Resistor_SMD:R_0805_2012Metric", (114.3, 76.2), {"1": "A", "2": "B"}),
            ("TP2", "Project_Symbols:TestPoint", "TP_B", "Project_Footprints:TestPoint_Pad_D1.5mm", (127.0, 76.2),
             {"1": "B"}),
        ],
        "placement": {"TP1": (110.0, 100.0), "R1": (115.0, 100.0), "TP2": (120.0, 100.0)},
        "tracks": [("A", ["TP1.1", "R1.1"]), ("B", ["R1.2", "TP2.1"])],
        "outline": ((105, 96), (125, 104)),
        "local_libraries": True,
    },
}
# Pin endpoint offsets in library coordinates (y up), from the official symbols.
PIN_OFFSETS = {
    "Device:R": {"1": (0, 3.81), "2": (0, -3.81)},
    "Connector_Generic:Conn_01x03": {"1": (-5.08, 2.54), "2": (-5.08, 0), "3": (-5.08, -2.54)},
    "Project_Symbols:TestPoint": {"1": (0, 0)},
}


def uid(project, label):
    # The divider keeps its original seeds so its schematic regenerates byte-identically.
    return str(uuid.uuid5(NS, label if project == "divider" else project + ":" + label))


def _block(text, name):
    start = text.index('\n\t(symbol "%s"\n' % name) + 1
    depth, i, in_str = 0, start, False
    while True:
        c = text[i]
        if in_str:
            if c == "\\":
                i += 1
            elif c == '"':
                in_str = False
        elif c == '"':
            in_str = True
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
        i += 1


def library_file(lib_id, project_dir):
    lib = lib_id.split(":")[0]
    if lib == "Project_Symbols":
        return project_dir / SYM_LIB
    return kicad_env.shared_support() / "symbols" / (lib + ".kicad_sym")


def extract_symbol(lib_id, project_dir):
    name = lib_id.split(":")[1]
    block = _block(library_file(lib_id, project_dir).read_text(), name)
    if "(extends" in block:
        raise SystemExit("Derived symbols are not supported by this fixture builder")
    block = block.replace('(symbol "%s"' % name, '(symbol "%s"' % lib_id, 1)
    return "\n".join("\t" + line for line in block.splitlines())


def lib_description(lib_id, project_dir):
    m = re.search(r'\(property "Description" "((?:[^"\\]|\\.)*)"', extract_symbol(lib_id, project_dir))
    return m.group(1) if m else ""


def prop(name, value, at, hide=False):
    hidden = "\n\t\t\t\t(hide yes)" if hide else ""
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %s %s 0)\n\t\t\t(effects\n\t\t\t\t(font\n'
            "\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)%s\n\t\t\t)\n\t\t)\n") % (name, value, at[0], at[1], hidden)


def schematic(project, spec, project_dir):
    root = uid(project, "root-sheet")
    libs = sorted({p[1] for p in spec["parts"]})
    out = [
        "(kicad_sch\n\t(version 20260306)\n\t(generator \"eeschema\")\n"
        "\t(generator_version \"10.0\")\n\t(uuid \"%s\")\n\t(paper \"A4\")\n" % root,
        "\t(title_block\n\t\t(title \"%s\")\n\t\t(rev \"fixture\")\n\t)\n" % spec["title"],
        "\t(lib_symbols\n" + "\n".join(extract_symbol(l, project_dir) for l in libs) + "\n\t)\n",
    ]
    for ref, lib_id, value, footprint, (x, y), pins in spec["parts"]:
        body = ("\t(symbol\n\t\t(lib_id \"%s\")\n\t\t(at %s %s 0)\n\t\t(unit 1)\n\t\t(exclude_from_sim no)\n"
                "\t\t(in_bom yes)\n\t\t(on_board yes)\n\t\t(dnp no)\n\t\t(uuid \"%s\")\n"
                % (lib_id, x, y, uid(project, "symbol-" + ref)))
        body += prop("Reference", ref, (x + 2.54, y - 1.27))
        body += prop("Value", value, (x + 2.54, y + 1.27))
        body += prop("Footprint", footprint, (x, y), hide=True)
        body += prop("Datasheet", "~", (x, y), hide=True)
        body += prop("Description", lib_description(lib_id, project_dir), (x, y), hide=True)
        for number in sorted(pins):
            body += '\t\t(pin "%s"\n\t\t\t(uuid "%s")\n\t\t)\n' % (number, uid(project, "pin-%s-%s" % (ref, number)))
        body += ("\t\t(instances\n\t\t\t(project \"%s\"\n\t\t\t\t(path \"/%s\"\n\t\t\t\t\t(reference \"%s\")\n"
                 "\t\t\t\t\t(unit 1)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n") % (project, root, ref)
        out.append(body)
        for number, net in sorted(pins.items()):
            dx, dy = PIN_OFFSETS[lib_id][number]
            px, py = round(x + dx, 4), round(y - dy, 4)
            angle, justify = (180, "right bottom") if lib_id.startswith("Connector") else (0, "left bottom")
            out.append("\t(label \"%s\"\n\t\t(at %s %s %d)\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size 1.27 1.27)\n"
                       "\t\t\t)\n\t\t\t(justify %s)\n\t\t)\n\t\t(uuid \"%s\")\n\t)\n"
                       % (net, px, py, angle, justify, uid(project, "label-%s-%s" % (ref, number))))
    out.append("\t(sheet_instances\n\t\t(path \"/\"\n\t\t\t(page \"1\")\n\t\t)\n\t)\n\t(embedded_fonts no)\n)\n")
    return "".join(out)


def write_local_libraries(project_dir):
    """Copy official parts into project libraries, keep attribution, register via ${KIPRJMOD}."""
    support = kicad_env.shared_support()
    official = (support / "symbols/Connector.kicad_sym").read_text()
    header = official[:official.index('\n\t(symbol "')]
    sym = project_dir / SYM_LIB
    sym.parent.mkdir(parents=True, exist_ok=True)
    sym.write_text(header + "\n" + _block(official, "TestPoint") + "\n)\n")
    fp_dir = project_dir / FP_LIB
    fp_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(support / "footprints/TestPoint.pretty/TestPoint_Pad_D1.5mm.kicad_mod", fp_dir)
    (project_dir / "sym-lib-table").write_text(
        '(sym_lib_table\n\t(version 7)\n\t(lib (name "Project_Symbols") (type "KiCad") '
        '(uri "${KIPRJMOD}/%s") (options "") (descr "Project-local symbols"))\n)\n' % SYM_LIB)
    (project_dir / "fp-lib-table").write_text(
        '(fp_lib_table\n\t(version 7)\n\t(lib (name "Project_Footprints") (type "KiCad") '
        '(uri "${KIPRJMOD}/%s") (options "") (descr "Project-local footprints"))\n)\n' % FP_LIB)
    (project_dir / "hardware/libraries/ATTRIBUTION.md").write_text(
        "# Library provenance\n\n"
        "`Project_Symbols:TestPoint` is copied unchanged from KiCad %s `Connector:TestPoint`;\n"
        "`Project_Footprints:TestPoint_Pad_D1.5mm` from `TestPoint:TestPoint_Pad_D1.5mm`.\n"
        "Source: KiCad official libraries, licensed CC-BY-SA 4.0 with the KiCad design\n"
        "exception (https://www.kicad.org/libraries/license/). Redistribution of these\n"
        "library items keeps this attribution and license.\n" % kicad_env.KICAD_VERSION)


PCB_SCRIPT = r"""
import json, sys, pcbnew
assert pcbnew.Version() == sys.argv[3], pcbnew.Version()
spec = json.loads(sys.argv[2])
board = pcbnew.LoadBoard(sys.argv[1])
mm = pcbnew.FromMM
def pt(x, y): return pcbnew.VECTOR2I(mm(x), mm(y))
nets = {}
for name in spec["nets"]:
    # Local schematic labels on the root sheet produce "/NAME" nets.
    net = pcbnew.NETINFO_ITEM(board, "/" + name)
    board.Add(net)
    nets[name] = net
pads = {}
for part in spec["parts"]:
    lib, name = part["footprint"].split(":")
    fp = pcbnew.FootprintLoad(spec["fp_dirs"][lib], name)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    fp.SetReference(part["ref"])
    fp.SetValue(part["value"])
    fp.SetField("Datasheet", "~")
    fp.SetField("Description", part["description"])
    fp.SetPath(pcbnew.KIID_PATH("/" + part["uuid"]))
    fp.SetSheetname("/")
    fp.SetSheetfile(spec["sheetfile"])
    fp.SetExcludedFromBOM(False)  # as "Update PCB from Schematic" does: symbols are in_bom yes
    fp.SetPosition(pt(*part["at"]))
    board.Add(fp)
    for pad in fp.Pads():
        net = part["pins"].get(pad.GetNumber())
        if net:
            pad.SetNet(nets[net])
            pads[part["ref"] + "." + pad.GetNumber()] = pad.GetPosition()
def coord(value, axis):
    if isinstance(value, str):
        p = pads[value]
        return p.x if axis == 0 else p.y
    return mm(value)
def point(p):
    if isinstance(p, str):
        return pads[p]
    return pcbnew.VECTOR2I(coord(p[0], 0), coord(p[1], 1))
for net, points in spec["tracks"]:
    pts = [point(p) for p in points]
    for a, b in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(a); t.SetEnd(b); t.SetWidth(mm(0.25))
        t.SetLayer(pcbnew.F_Cu); t.SetNet(nets[net]); board.Add(t)
(x1, y1), (x2, y2) = spec["outline"]
edge = pcbnew.PCB_SHAPE(board)
edge.SetShape(pcbnew.SHAPE_T_RECT)
edge.SetStart(pt(x1, y1)); edge.SetEnd(pt(x2, y2))
edge.SetLayer(pcbnew.Edge_Cuts); edge.SetWidth(mm(0.05))
board.Add(edge)
assert pcbnew.SaveBoard(sys.argv[1], board)
"""


def build(project, output):
    spec = PROJECTS[project]
    output = Path(output)
    python = kicad_env.bundled_python()
    if not python or not kicad_env.shared_support():
        raise SystemExit("KiCad %s with bundled Python is required." % kicad_env.KICAD_VERSION)
    with tempfile.TemporaryDirectory() as tmp:
        stage = Path(tmp) / project
        stage.mkdir()
        defaults = ROOT / "hardware/native-defaults"
        shutil.copy2(defaults / "default.kicad_pro", stage / (project + ".kicad_pro"))
        shutil.copy2(defaults / "default.kicad_pcb", stage / (project + ".kicad_pcb"))
        fp_dirs = {}
        if spec["local_libraries"]:
            write_local_libraries(stage)
            fp_dirs["Project_Footprints"] = str(stage / FP_LIB)
        for part in spec["parts"]:
            lib = part[3].split(":")[0]
            fp_dirs.setdefault(lib, str(kicad_env.shared_support() / "footprints" / (lib + ".pretty")))
        (stage / (project + ".kicad_sch")).write_text(schematic(project, spec, stage))
        payload = {
            "fp_dirs": fp_dirs, "sheetfile": project + ".kicad_sch", "tracks": spec["tracks"],
            "outline": spec["outline"], "nets": sorted({n for *_, pins in spec["parts"] for n in pins.values()}),
            "parts": [{"ref": r, "value": v, "footprint": f, "uuid": uid(project, "symbol-" + r),
                       "description": lib_description(l, stage), "at": spec["placement"][r], "pins": pins}
                      for r, l, v, f, _, pins in spec["parts"]],
        }
        result = subprocess.run([str(python), "-c", PCB_SCRIPT, str(stage / (project + ".kicad_pcb")),
                                 json.dumps(payload), kicad_env.KICAD_VERSION], capture_output=True, text=True)
        if result.returncode:
            raise SystemExit("pcbnew fixture build failed:\n" + result.stderr[-3000:])
        for state in stage.glob("*.kicad_prl"):
            state.unlink()  # editor-local state is never fixture source
        (stage / "README.md").write_text(
            "# Reference project: %s\n\nGenerated by `qa/fixtures/build_fixtures.py` with KiCad %s.\n"
            "Tooling reference only: not a reviewed or validated circuit. Purpose and validation\n"
            "status: `qa/fixtures/README.md`. Regeneration is semantically identical; pcbnew\n"
            "assigns fresh board item UUIDs.\n" % (project, kicad_env.KICAD_VERSION))
        if output.exists():
            marker = output / "README.md"
            if not marker.is_file() or "build_fixtures.py" not in marker.read_text():
                raise SystemExit("Refusing to replace a directory not created by this builder: %s" % output)
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(stage, output)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", choices=sorted(PROJECTS))
    parser.add_argument("--output-root", default=str(ROOT / "qa/fixtures"))
    args = parser.parse_args()
    for name in [args.only] if args.only else sorted(PROJECTS):
        print(build(name, Path(args.output_root) / name))
