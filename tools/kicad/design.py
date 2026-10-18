"""Read-only model of a KiCad project's schematic hierarchy and board."""

from pathlib import Path

from tools.core import sexpr
from tools.core.common import KitError


def _flag(node, name, default):
    value = sexpr.flag(node, name)
    return default if value is None else value


def schematic_symbols(root_schematic):
    """Placed symbols across the hierarchy, one record per reference designator."""
    root_schematic = Path(root_schematic)
    pending, seen, power_libs = [root_schematic], set(), set()
    records = {}
    sheets = []
    while pending:
        path = pending.pop()
        if path.resolve() in seen:
            continue
        seen.add(path.resolve())
        try:
            tree = sexpr.load(path)
        except (OSError, sexpr.ParseError) as exc:
            raise KitError("Cannot read schematic %s: %s" % (path, exc), 13)
        sheets.append(str(path))
        libs = sexpr.child(tree, "lib_symbols") or []
        for lib in sexpr.children(libs, "symbol"):
            if sexpr.child(lib, "power") is not None:
                power_libs.add(lib[1])
        for sheet in sexpr.children(tree, "sheet"):
            sub = sexpr.properties(sheet).get("Sheetfile")
            if sub:
                pending.append(path.parent / sub)
        for sym in sexpr.children(tree, "symbol"):
            props = sexpr.properties(sym)
            lib_id = sexpr.value(sym, "lib_id", "")
            refs = set()
            for inst in sexpr.children(sexpr.child(sym, "instances") or [], "project"):
                for p in sexpr.children(inst, "path"):
                    if sexpr.value(p, "reference"):
                        refs.add(sexpr.value(p, "reference"))
            if not refs:
                refs.add(props.get("Reference", "?"))
            for ref in refs:
                power = lib_id in power_libs or ref.startswith("#")
                records[ref] = {
                    "reference": ref,
                    "lib_id": lib_id,
                    "value": props.get("Value", ""),
                    "footprint": props.get("Footprint", ""),
                    "datasheet": props.get("Datasheet", ""),
                    "fields": props,
                    "in_bom": _flag(sym, "in_bom", True),
                    "on_board": _flag(sym, "on_board", True),
                    "dnp": _flag(sym, "dnp", False),
                    "power": power,
                    "sheet": str(path.name),
                }
    return {"sheets": sheets, "symbols": [records[k] for k in sorted(records, key=_ref_key)]}


def board_footprints(board):
    try:
        tree = sexpr.load(board)
    except (OSError, sexpr.ParseError) as exc:
        raise KitError("Cannot read board %s: %s" % (board, exc), 13)
    result = []
    for fp in sexpr.children(tree, "footprint"):
        props = sexpr.properties(fp)
        attr = sexpr.child(fp, "attr") or []
        models = []
        for model in sexpr.children(fp, "model"):
            models.append({"path": model[1], "hidden": sexpr.flag(model, "hide") is True})
        result.append(
            {
                "reference": props.get("Reference", "?"),
                "lib_id": fp[1] if len(fp) > 1 and isinstance(fp[1], str) else "",
                "value": props.get("Value", ""),
                "attributes": [str(a) for a in attr[1:]],
                "models": models,
                "pads": len(sexpr.children(fp, "pad")),
            }
        )
    return sorted(result, key=lambda f: _ref_key(f["reference"]))


def _ref_key(ref):
    prefix = ref.rstrip("0123456789")
    digits = ref[len(prefix):]
    return (prefix, int(digits) if digits else -1, ref)
