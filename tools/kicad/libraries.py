"""Symbol/footprint library tables: resolution, validation, conservative registration.

Resolution follows KiCad 10: project tables (``${KIPRJMOD}``) override global
tables in the versioned config directory; ``(type "Table")`` entries nest
another table whose libraries keep their own nicknames.
"""

from functools import lru_cache
from pathlib import Path
import re

from tools.core import kicad_env
from tools.core import sexpr
from tools.core.common import KitError, check_locks

TABLES = {"symbol": ("sym-lib-table", "sym_lib_table"), "footprint": ("fp-lib-table", "fp_lib_table")}


def parse_table(path, variables, _seen=None):
    """Flattened [{name, type, uri, path, unresolved, source}] for one table file."""
    path = Path(path)
    seen = _seen if _seen is not None else set()
    if path.resolve() in seen:
        return []
    seen.add(path.resolve())
    tree = sexpr.load(path)
    entries = []
    for lib in sexpr.children(tree, "lib"):
        uri = sexpr.value(lib, "uri", "")
        expanded, missing = kicad_env.expand(uri, variables)
        entry = {
            "name": sexpr.value(lib, "name", ""),
            "type": sexpr.value(lib, "type", "KiCad"),
            "uri": uri,
            "path": expanded,
            "unresolved": missing,
            "source": str(path),
            "disabled": sexpr.child(lib, "disabled") is not None,
        }
        if entry["type"] == "Table" and not missing and Path(expanded).is_file():
            entries.extend(parse_table(expanded, variables, seen))
        else:
            entries.append(entry)
    return entries


class LibraryTables:
    def __init__(self, project_root=None):
        self.root = Path(project_root).resolve() if project_root else None
        self.variables = kicad_env.path_vars(self.root)
        self.problems = []
        self.tables = {}
        for kind, (filename, _header) in TABLES.items():
            merged = {}
            global_table = kicad_env.config_dir() / filename
            if global_table.is_file():
                merged.update(self._load(global_table))
            else:
                self.problems.append("Global %s missing: %s" % (filename, global_table))
            if self.root and (self.root / filename).is_file():
                merged.update(self._load(self.root / filename))  # project overrides global
            self.tables[kind] = merged

    def _load(self, path):
        try:
            return {e["name"]: e for e in parse_table(path, self.variables)}
        except (OSError, sexpr.ParseError) as exc:
            self.problems.append("Unreadable library table %s: %s" % (path, exc))
            return {}

    def resolve(self, kind, lib_id):
        """Check one "Nickname:Item" reference; returns a finding dict or None if valid."""
        if ":" not in lib_id:
            return {"lib_id": lib_id, "problem": "missing library nickname"}
        nickname, item = lib_id.split(":", 1)
        entry = self.tables[kind].get(nickname)
        if entry is None:
            return {"lib_id": lib_id, "problem": "library nickname not in any %s table" % kind}
        if entry["disabled"]:
            return {"lib_id": lib_id, "problem": "library is disabled", "table": entry["source"]}
        if entry["unresolved"]:
            return {"lib_id": lib_id, "problem": "unresolved path variable(s): " + ", ".join(entry["unresolved"]),
                    "uri": entry["uri"]}
        path = Path(entry["path"])
        if kind == "symbol":
            if not path.is_file():
                return {"lib_id": lib_id, "problem": "symbol library file missing", "path": str(path)}
            if item not in symbol_names(str(path), path.stat().st_mtime):
                return {"lib_id": lib_id, "problem": "symbol not found in library", "path": str(path)}
        else:
            if not path.is_dir():
                return {"lib_id": lib_id, "problem": "footprint library directory missing", "path": str(path)}
            if not (path / (item + ".kicad_mod")).is_file():
                return {"lib_id": lib_id, "problem": "footprint not found in library", "path": str(path)}
        return None

    def summary(self):
        result = {"problems": list(self.problems)}
        for kind, entries in self.tables.items():
            broken = []
            for e in entries.values():
                if e["disabled"]:
                    continue
                target = Path(e["path"])
                ok = not e["unresolved"] and (target.is_file() if kind == "symbol" else target.is_dir())
                if not ok:
                    broken.append({"name": e["name"], "uri": e["uri"], "unresolved": e["unresolved"]})
            result[kind] = {"libraries": len(entries), "broken": broken}
        return result


_SYMBOL = re.compile(r'^\t\(symbol "((?:[^"\\]|\\.)*)"', re.M)


@lru_cache(maxsize=256)
def symbol_names(path, _mtime):
    """Top-level symbol names; KiCad writes one tab-indented entry per symbol."""
    return frozenset(_SYMBOL.findall(Path(path).read_text(encoding="utf-8")))


def quoted(text):
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def register_library(root, kind, name, source):
    """Add a project-local library under hardware/libraries via ${KIPRJMOD}.

    Existing entries are never replaced; an identical entry is accepted as-is.
    """
    root = Path(root).resolve()
    source = Path(source).resolve()
    check_locks(root)
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", name):
        raise KitError("Use a simple library name (letters, digits, _, -).")
    try:
        rel = source.relative_to(root / "hardware/libraries")
    except ValueError:
        raise KitError("Libraries must already exist inside hardware/libraries; no vendor downloads are invented.")
    if kind not in TABLES:
        raise KitError("Choose symbol or footprint.")
    filename, header = TABLES[kind]
    valid = source.is_file() and source.suffix == ".kicad_sym" if kind == "symbol" else (
        source.is_dir() and source.suffix == ".pretty")
    if not valid:
        raise KitError("Library does not exist or has the wrong format.")
    uri = "${KIPRJMOD}/hardware/libraries/" + rel.as_posix()
    entry = '\t(lib (name %s) (type "KiCad") (uri %s) (options "") (descr ""))' % (quoted(name), quoted(uri))
    table = root / filename
    text = table.read_text() if table.exists() else "(%s\n\t(version 7)\n)\n" % header
    if not text.lstrip().startswith("(" + header) or not text.rstrip().endswith(")"):
        raise KitError("Existing table is not recognized; edit it in KiCad.")
    try:
        existing = {e["name"]: e for e in parse_table(table, {})} if table.exists() else {}
    except sexpr.ParseError:
        raise KitError("Existing table is unbalanced; use KiCad's library manager.")
    if name in existing:
        if existing[name]["uri"] == uri:
            return table
        raise KitError("Library name already registered with a different URI; existing entry was preserved.")
    pos = text.rstrip().rfind(")")
    table.write_text(text[:pos].rstrip("\n") + "\n" + entry + "\n)\n")
    return table
