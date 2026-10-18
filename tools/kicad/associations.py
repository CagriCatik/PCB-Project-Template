"""Symbol-to-footprint association check: every electrical symbol pin needs a pad.

Authoritative data: the symbol definitions embedded in the schematic (copied
from the symbol library) and the assigned footprint in its footprint library.
A pin without a matching pad number would silently drop a connection from the
PCB, the classic "wrong footprint for this symbol" failure.
"""

from functools import lru_cache
from pathlib import Path

from tools.core import sexpr


def symbol_pins(sheet_files):
    """{lib_id: {pin_number: electrical_type}} from lib_symbols of every sheet."""
    result = {}
    for sheet in sheet_files:
        result.update(_sheet_pins(sexpr.load(sheet)))
    return result


def _sheet_pins(tree):
    result = {}
    for lib in sexpr.children(sexpr.child(tree, "lib_symbols") or [], "symbol"):
        pins = {}

        def walk(node):
            for child in node[1:]:
                if isinstance(child, list) and child:
                    if child[0] == "pin" and len(child) > 1:
                        number = sexpr.value(child, "number")
                        if number is not None:
                            pins[str(number)] = str(child[1])
                    else:
                        walk(child)

        walk(lib)
        result[lib[1]] = pins
    return result


@lru_cache(maxsize=512)
def footprint_pads(path, _mtime):
    tree = sexpr.load(path)
    return frozenset(str(p[1]) for p in sexpr.children(tree, "pad") if len(p) > 1 and str(p[1]))


def check(model, tables):
    """Findings for symbols whose footprint lacks pads for electrical pins."""
    pins_by_lib = symbol_pins(model["sheets"])
    findings, checked = [], 0
    for sym in model["symbols"]:
        if sym["power"] or not sym["on_board"] or not sym["footprint"] or ":" not in sym["footprint"]:
            continue
        nickname, name = sym["footprint"].split(":", 1)
        entry = tables.tables["footprint"].get(nickname)
        if not entry or entry["unresolved"]:
            continue  # reported by library_references
        path = Path(entry["path"]) / (name + ".kicad_mod")
        if not path.is_file():
            continue
        pins = pins_by_lib.get(sym["lib_id"], {})
        electrical = {n for n, kind in pins.items() if kind != "no_connect"}
        pads = footprint_pads(str(path), path.stat().st_mtime)
        checked += 1
        missing = sorted(electrical - pads, key=_natural)
        if missing:
            findings.append({"reference": sym["reference"], "footprint": sym["footprint"],
                             "problem": "symbol pin(s) without a pad: " + ", ".join(missing),
                             "unused_pads": sorted(pads - set(pins), key=_natural)})
    return findings, checked


def _natural(text):
    return (0, int(text), "") if text.isdigit() else (1, 0, text)
