"""Portability check: a project must not depend on machine-specific absolute paths.

Accepted path forms: ${KIPRJMOD}-relative, KiCad's own versioned variables
(${KICAD10_*}), and plain relative paths. Absolute paths and user-defined path
variables only work on the machine that defines them; older versioned variables
(e.g. ${KICAD9_3DMODEL_DIR}) are not resolved by KiCad 10.0.7.
"""

import json
from pathlib import Path
import re

from tools.core import sexpr
from tools.core.common import project_files

_VAR = re.compile(r"\$\{([A-Za-z0-9_]+)\}")
_ABS = re.compile(r"^(/|~|[A-Za-z]:[\\/]|\\\\)")
_HOME = re.compile(r"(/Users/[^/\"]+|/home/[^/\"]+|[A-Za-z]:\\\\Users\\\\)")


def classify(path_text):
    """None if portable, else a short reason."""
    if not path_text:
        return None
    names = _VAR.findall(path_text)
    for name in names:
        if name == "KIPRJMOD" or re.fullmatch(r"KICAD10_[A-Z0-9_]+", name):
            continue
        if re.fullmatch(r"KICAD\d+_[A-Z0-9_]+", name):
            return "legacy KiCad variable ${%s} (not resolved by KiCad 10)" % name
        return "user-defined variable ${%s} must be configured on every machine" % name
    if not names and _ABS.match(path_text):
        return "absolute path"
    return None


def check(root):
    root = Path(root).resolve()
    pro, sch, pcb = project_files(root)
    findings = []

    def add(where, value, reason):
        findings.append({"file": where, "path": value, "problem": reason})

    for table in ("sym-lib-table", "fp-lib-table"):
        path = root / table
        if path.is_file():
            for lib in sexpr.children(sexpr.load(path), "lib"):
                uri = sexpr.value(lib, "uri", "")
                reason = classify(uri)
                if reason:
                    add(table, uri, reason)
                elif not _VAR.search(uri) and not _ABS.match(uri):
                    add(table, uri, "relative URI without ${KIPRJMOD} resolves against KiCad's working directory")
    board = sexpr.load(pcb)
    for fp in sexpr.children(board, "footprint"):
        ref = sexpr.properties(fp).get("Reference", "?")
        for model in sexpr.children(fp, "model"):
            reason = classify(model[1])
            if reason:
                add(pcb.name + " " + ref, model[1], reason)
    pending, seen = [sch], set()
    while pending:
        current = pending.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)
        for sheet in sexpr.children(sexpr.load(current), "sheet"):
            target = sexpr.properties(sheet).get("Sheetfile", "")
            reason = classify(target)
            if reason:
                add(current.name, target, reason)
            else:
                pending.append(current.parent / target)
    text = pro.read_text()
    for match in sorted(set(_HOME.findall(text))):
        add(pro.name, match, "user home directory path in project settings")
    try:
        json.loads(text)
    except ValueError as exc:
        add(pro.name, "", "project file is not valid JSON: %s" % exc)
    return findings
