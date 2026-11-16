"""Layout-independent native inventory and canonical KiCad XML netlist reader.

Never derives connectivity from drawing coordinates. KiCad is the net resolver.
Repeated sheet instances are retained in the hierarchy; native symbols are keyed
by file and UUID, not reference (which is unsafe for multi-unit components).
"""
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from tools.core import sexpr as sx
from tools.core.common import VERSION, KitError, sha256

SCHEMA = 1


def _normal(node):
    return json.loads(json.dumps(node))


def inventory(schematic):
    root = Path(schematic).resolve()
    base = root.parent
    files, active, hashes = {}, set(), {}

    def visit(path):
        path = path.resolve()
        if not path.is_relative_to(base):
            raise KitError("External sheet is not portable: %s" % path)
        if path in active:
            raise KitError("Cyclic schematic hierarchy: %s" % path)
        if path in files:
            return
        active.add(path)
        raw = path.read_bytes()
        tree = sx.parse(raw.decode("utf-8"))
        if sx.head(tree) != "kicad_sch":
            raise KitError("Not a KiCad schematic: %s" % path)
        rel = path.relative_to(base).as_posix()
        hashes[rel] = hashlib.sha256(raw).hexdigest()
        symbols, sheets, labels = [], [], []
        for symbol in sx.children(tree, "symbol"):
            symbols.append({
                "uuid": sx.value(symbol, "uuid"), "lib_id": sx.value(symbol, "lib_id"),
                "unit": sx.value(symbol, "unit"), "fields": sx.properties(symbol),
                "flags": {k: sx.flag(symbol, k) for k in
                          ("in_bom", "on_board", "dnp", "exclude_from_sim", "in_pos_files")},
                "instances": _normal(sx.child(symbol, "instances")),
                "pins": sorted([_normal(p) for p in sx.children(symbol, "pin")], key=str),
            })
        for sheet in sx.children(tree, "sheet"):
            props = sx.properties(sheet)
            filename = props.get("Sheetfile") or props.get("Sheet file")
            if not filename:
                raise KitError("Sheet without Sheetfile in %s" % rel)
            sheets.append({"uuid": sx.value(sheet, "uuid"), "fields": props,
                           "instances": _normal(sx.child(sheet, "instances")),
                           "pins": sorted([{"name": p[1], "shape": sx.value(p, "shape"),
                                            "uuid": sx.value(p, "uuid")}
                                           for p in sx.children(sheet, "pin")], key=str)})
            visit(path.parent / filename)
        for kind in ("label", "global_label", "hierarchical_label"):
            for label in sx.children(tree, kind):
                labels.append({"kind": kind, "name": label[1],
                               "shape": sx.value(label, "shape"), "uuid": sx.value(label, "uuid")})
        libraries = sx.child(tree, "lib_symbols")
        files[path] = {
            "file": rel, "uuid": sx.value(tree, "uuid"),
            "symbols": sorted(symbols, key=lambda s: str(s["uuid"])),
            "sheets": sorted(sheets, key=lambda s: str(s["uuid"])),
            "labels": sorted(labels, key=str),
            "no_connect_count": len(sx.children(tree, "no_connect")),
            "library_digest": hashlib.sha256(json.dumps(libraries, sort_keys=True).encode()).hexdigest(),
        }
        active.remove(path)

    visit(root)
    for extra in (root.with_suffix(".kicad_pro"), base / "sym-lib-table"):
        if extra.is_file():
            hashes[extra.name] = sha256(extra)
    return {"root": root.name, "sheets": sorted(files.values(), key=lambda f: f["file"])}, hashes


def netlist(path):
    tree = ET.parse(path).getroot()
    if tree.tag != "export" or tree.find("nets") is None or tree.find("components") is None:
        raise KitError("Missing KiCad XML netlist sections")
    components = []
    for c in tree.findall("components/comp"):
        # sheetpath + ref identifies reused sheet instances, even if tstamp is shared.
        components.append({"ref": c.get("ref"), "path": dict(c.find("sheetpath").attrib)
                           if c.find("sheetpath") is not None else {},
                           "value": c.findtext("value"), "footprint": c.findtext("footprint"),
                           "datasheet": c.findtext("datasheet"),
                           "fields": sorted([(f.get("name"), f.text or "") for f in c.findall("fields/field")]),
                           "properties": sorted([dict(p.attrib) for p in c.findall("property")], key=str),
                           "tstamps": c.findtext("tstamps")})
    nets = []
    for n in tree.findall("nets/net"):
        members = sorted([dict(p.attrib) for p in n.findall("node")], key=lambda x: json.dumps(x, sort_keys=True))
        # Generated names change with KiCad naming choices; partition is still compared.
        name = n.get("name", "")
        named = not re.search(r"(?:^|/)(?:Net-\(|unconnected-\()", name)
        nets.append({"name": name if named else None, "members": members})
    return {"components": sorted(components, key=lambda c: json.dumps(c, sort_keys=True)),
            "nets": sorted(nets, key=lambda n: json.dumps(n, sort_keys=True))}


def compare(before, after):
    for data in (before, after):
        if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("native"), dict) or not isinstance(data.get("electrical"), dict):
            raise KitError("Unsupported or incomplete schematic snapshot")
    differences = []
    for section in ("native", "electrical"):
        _diff(before[section], after[section], section, differences)
    return {"schema": SCHEMA, "identical": not differences, "differences": differences,
            "scope": "net partition, explicit names, components, native identities and interfaces; not an electrical safety approval",
            "toolchain_match": before.get("kicad") == after.get("kicad"),
            "toolchain_supported": all(d.get("kicad") == VERSION and d.get("version_status") == "TESTED"
                                       for d in (before, after))}


def _diff(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):
            if key not in a or key not in b:
                out.append({"path": path + "/" + key, "before": a.get(key), "after": b.get(key)})
            else:
                _diff(a[key], b[key], path + "/" + key, out)
    elif a != b:
        out.append({"path": path, "before": a, "after": b})
