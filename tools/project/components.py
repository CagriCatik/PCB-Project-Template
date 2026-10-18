"""Project component records: one reviewed JSON file per manufacturer part.

Records live in ``components/approved-parts/<manufacturer>__<mpn>.json`` of a
project. They link a real manufacturer part number to its datasheet, KiCad
symbol/footprint/3D model, ratings, procurement data and approval state.
Nothing here downloads or invents part data; validation only reports.
"""

from datetime import date
import json
from pathlib import Path
import re

from tools.core import kicad_env
from tools.core.common import KitError, sha256, write_json
from tools.kicad.libraries import LibraryTables

STATUSES = ("candidate", "approved", "restricted", "obsolete", "rejected")
LIFECYCLES = ("active", "nrnd", "eol", "obsolete", "unknown")
PART_DIR = "components/approved-parts"


def slug(text):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-") or "unnamed"


def record_path(project, manufacturer, mpn):
    return Path(project) / PART_DIR / ("%s__%s.json" % (slug(manufacturer), slug(mpn)))


def template_record(manufacturer, mpn):
    return {
        "schema": 1,
        "manufacturer": manufacturer,
        "mpn": mpn,
        "description": "",
        "datasheet": {"url": "", "revision": "", "local_file": None, "sha256": None, "retrieved_on": None},
        "kicad": {"symbol": "", "footprint": "", "model_3d": None, "spice_model": None},
        "ratings": {},
        "procurement": [],
        "approval": {"status": "candidate", "approved_by": "", "date": "", "notes": ""},
    }


def load_records(project):
    folder = Path(project) / PART_DIR
    records, problems = [], []
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        try:
            data = json.loads(path.read_text())
            if not isinstance(data, dict):
                raise ValueError("top level must be an object")
            records.append((path, data))
        except (OSError, ValueError) as exc:
            problems.append({"file": str(path), "problem": "unreadable JSON: %s" % exc})
    return records, problems


def _need(cond, findings, path, message):
    if not cond:
        findings.append({"file": str(path), "problem": message})


def validate_record(project, path, data, tables=None):
    """Schema, file and library checks for one record; returns findings."""
    f = []
    project = Path(project)
    _need(data.get("schema") == 1, f, path, "schema must be 1")
    for key in ("manufacturer", "mpn"):
        _need(isinstance(data.get(key), str) and data.get(key).strip(), f, path, "missing " + key)
    if f:
        return f
    expected = record_path(project, data["manufacturer"], data["mpn"]).name
    _need(Path(path).name == expected, f, path, "file name should be " + expected)
    ds = data.get("datasheet") or {}
    url = ds.get("url") or ""
    _need(url.startswith("https://") or ds.get("local_file"), f, path, "datasheet needs an https URL or local file")
    if ds.get("local_file"):
        local = (project / ds["local_file"]).resolve()
        if project.resolve() not in local.parents or not local.is_file():
            f.append({"file": str(path), "problem": "datasheet local_file missing: %s" % ds["local_file"]})
        elif ds.get("sha256") and sha256(local) != ds["sha256"]:
            f.append({"file": str(path), "problem": "datasheet sha256 mismatch: %s" % ds["local_file"]})
    kicad = data.get("kicad") or {}
    tables = tables or LibraryTables(project)
    for kind, key in (("symbol", "symbol"), ("footprint", "footprint")):
        ref = kicad.get(key) or ""
        if not ref:
            f.append({"file": str(path), "problem": "kicad.%s not set" % key})
            continue
        problem = tables.resolve(kind, ref)
        if problem:
            f.append({"file": str(path), "problem": "kicad.%s %s: %s" % (key, ref, problem["problem"])})
    if kicad.get("model_3d"):
        resolved, missing = kicad_env.expand(kicad["model_3d"], tables.variables)
        if missing or not Path(resolved).is_file():
            f.append({"file": str(path), "problem": "kicad.model_3d not found: %s" % kicad["model_3d"]})
    for entry in data.get("procurement") or []:
        _need(entry.get("lifecycle", "unknown") in LIFECYCLES, f, path, "procurement lifecycle invalid")
    approval = data.get("approval") or {}
    status = approval.get("status")
    _need(status in STATUSES, f, path, "approval.status must be one of " + "/".join(STATUSES))
    if status == "approved":
        _need(approval.get("approved_by"), f, path, "approved part needs approval.approved_by")
        _need(ds.get("revision"), f, path, "approved part needs datasheet.revision")
        _need(data.get("ratings"), f, path, "approved part needs ratings taken from the datasheet")
        _need(data.get("procurement"), f, path, "approved part needs procurement data")
        try:
            date.fromisoformat(approval.get("date") or "")
        except ValueError:
            f.append({"file": str(path), "problem": "approval.date must be ISO YYYY-MM-DD"})
    return f


def validate(project):
    project = Path(project).resolve()
    records, findings = load_records(project)
    tables = LibraryTables(project)
    seen = {}
    for path, data in records:
        findings.extend(validate_record(project, path, data, tables))
        key = (str(data.get("manufacturer", "")).lower(), str(data.get("mpn", "")).lower())
        if key in seen:
            findings.append({"file": str(path), "problem": "duplicate of " + seen[key]})
        seen[key] = str(path)
    return {
        "records": len(records),
        "approved": sum(1 for _, d in records if (d.get("approval") or {}).get("status") == "approved"),
        "findings": findings,
        "status": "PASS" if not findings else "FAIL",
    }


def index(project):
    records, _ = load_records(project)
    return {(str(d.get("mpn", "")).lower(), str(d.get("manufacturer", "")).lower()): (p, d) for p, d in records}


def add(project, manufacturer, mpn, symbol="", footprint="", datasheet_url="", revision=""):
    """Create a candidate record; an existing record is never overwritten."""
    if not manufacturer.strip() or not mpn.strip():
        raise KitError("Manufacturer and MPN are required.")
    path = record_path(project, manufacturer, mpn)
    if path.exists():
        raise KitError("Component record already exists; edit it explicitly: %s" % path)
    data = template_record(manufacturer.strip(), mpn.strip())
    data["kicad"].update({"symbol": symbol, "footprint": footprint})
    data["datasheet"].update({"url": datasheet_url, "revision": revision})
    write_json(path, data)
    return path
