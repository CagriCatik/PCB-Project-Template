"""Configurable quality gates for one KiCad project (read-only on design files).

Gates: erc, drc, schematic_parity, library_references, portability,
footprint_assignment, pin_pad_mapping, component_metadata, models_3d, bom,
firmware, thermal. Each project configures gate
severity in ``qa/verification.json`` as required / advisory / disabled.
A PASS is a tooling result only; it is not evidence of electrical, thermal or
fabrication correctness.
"""

import json
from pathlib import Path
import tempfile

from tools.project import components
from tools.kicad import design
from tools.core import kicad_env, sexpr
from tools.core.common import KitError, check_locks, now, project_files, source_hashes, write_json
from tools.kicad.cli import KiCadCLI, summarize_drc, summarize_erc
from tools.kicad.libraries import LibraryTables

GATES = (
    "erc",
    "drc",
    "schematic_parity",
    "library_references",
    "portability",
    "footprint_assignment",
    "pin_pad_mapping",
    "component_metadata",
    "models_3d",
    "bom",
    "firmware",
    "thermal",
)
SEVERITIES = ("required", "advisory", "disabled")
DEFAULT_CONFIG = {
    "schema": 1,
    "gates": {
        "erc": "required",
        "drc": "required",
        "schematic_parity": "required",
        "library_references": "required",
        "portability": "required",
        "footprint_assignment": "required",
        "pin_pad_mapping": "required",
        "component_metadata": "advisory",
        "models_3d": "advisory",
        "bom": "advisory",
        "firmware": "disabled",
        "thermal": "disabled",
    },
    "metadata_fields": ["Manufacturer", "MPN"],
    "manufacturer_field": "Manufacturer",
    "mpn_field": "MPN",
    # A formal release additionally forces these gates to be required.
    "release_gates": [
        "erc", "drc", "schematic_parity", "library_references", "portability",
        "footprint_assignment", "pin_pad_mapping", "component_metadata", "models_3d", "bom",
    ],
}


def load_config(root):
    path = Path(root) / "qa/verification.json"
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    if path.is_file():
        try:
            data = json.loads(path.read_text())
        except ValueError as exc:
            raise KitError("qa/verification.json is not valid JSON: %s" % exc)
        config["gates"].update(data.get("gates", {}))
        for key in ("metadata_fields", "manufacturer_field", "mpn_field", "release_gates"):
            if key in data:
                config[key] = data[key]
    for gate, severity in config["gates"].items():
        if gate not in GATES or severity not in SEVERITIES:
            raise KitError("qa/verification.json: invalid gate %r=%r" % (gate, severity))
    return config


def _result(findings, status=None, **extra):
    return {"status": status or ("PASS" if not findings else "FAIL"), "count": len(findings),
            "findings": findings, **extra}


def gate_library_references(model, footprints, tables):
    findings = []
    for sym in model["symbols"]:
        problem = tables.resolve("symbol", sym["lib_id"])
        if problem:
            findings.append({"reference": sym["reference"], **problem})
        if sym["footprint"] and not sym["power"]:
            problem = tables.resolve("footprint", sym["footprint"])
            if problem:
                findings.append({"reference": sym["reference"], "field": "Footprint", **problem})
    for fp in footprints:
        problem = tables.resolve("footprint", fp["lib_id"])
        if problem:
            findings.append({"reference": fp["reference"], "item": "board footprint", **problem})
    return _result(findings, table_problems=tables.problems)


def gate_footprint_assignment(model):
    findings = [
        {"reference": s["reference"], "problem": "no footprint assigned"}
        for s in model["symbols"]
        if s["on_board"] and not s["power"] and not s["footprint"].strip()
    ]
    return _result(findings)


def _bom_symbols(model):
    return [s for s in model["symbols"] if s["in_bom"] and not s["power"] and not s["dnp"]]


def gate_component_metadata(model, fields):
    findings = []
    for s in _bom_symbols(model):
        missing = [f for f in fields if not str(s["fields"].get(f, "")).strip()]
        if s["datasheet"].strip() in ("", "~"):
            missing.append("Datasheet")
        if missing:
            findings.append({"reference": s["reference"], "missing": missing})
    return _result(findings, checked=len(_bom_symbols(model)))


def gate_models_3d(footprints, variables):
    findings, checked = [], 0
    for fp in footprints:
        if "board_only" in fp["attributes"] or ("exclude_from_bom" in fp["attributes"] and not fp["models"]):
            continue  # graphics/mechanical items without a physical component
        checked += 1
        visible = [m for m in fp["models"] if not m["hidden"]]
        if not visible:
            findings.append({"reference": fp["reference"], "problem": "no 3D model assigned"})
            continue
        for m in visible:
            resolved, missing = kicad_env.expand(m["path"], variables)
            if missing:
                findings.append({"reference": fp["reference"], "model": m["path"],
                                 "problem": "unresolved variable(s): " + ", ".join(missing)})
            elif not Path(resolved).is_file():
                findings.append({"reference": fp["reference"], "model": m["path"], "problem": "model file missing"})
    return _result(findings, checked=checked)


def gate_bom(root, model, mfr_field, mpn_field):
    """Every placed BOM line must map to a valid, approved component record."""
    records = components.index(root)
    findings = []
    for s in _bom_symbols(model):
        mpn = str(s["fields"].get(mpn_field, "")).strip()
        mfr = str(s["fields"].get(mfr_field, "")).strip()
        if not mpn:
            findings.append({"reference": s["reference"], "problem": "no %s field" % mpn_field})
            continue
        hit = records.get((mpn.lower(), mfr.lower()))
        if not hit:
            findings.append({"reference": s["reference"], "mpn": mpn, "problem": "no component record"})
            continue
        path, data = hit
        status = (data.get("approval") or {}).get("status")
        if status != "approved":
            findings.append({"reference": s["reference"], "mpn": mpn, "problem": "component status is %s" % status})
        expected = (data.get("kicad") or {}).get("footprint")
        if expected and expected != s["footprint"]:
            findings.append({"reference": s["reference"], "mpn": mpn,
                             "problem": "footprint %s differs from record %s" % (s["footprint"], expected)})
    record_check = components.validate(root)
    for f in record_check["findings"]:
        findings.append({"record": f["file"], "problem": f["problem"]})
    return _result(findings, checked=len(_bom_symbols(model)), records=record_check["records"])


def verify(root, cli=None, gates=None, release=False):
    """Run all non-disabled gates; writes reports under qa/generated/verification/."""
    root = Path(root).resolve()
    files = project_files(root)
    check_locks(root)
    config = load_config(root)
    severity = dict(config["gates"])
    if release:
        for gate in config["release_gates"]:
            severity[gate] = "required"
    selected = [g for g in GATES if severity[g] != "disabled" and (gates is None or g in gates)]
    cli = cli or KiCadCLI()
    parent = root / "qa/generated/verification"
    parent.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=now().replace(":", "")[:15] + "-", dir=parent))
    before = source_hashes(root)
    results, commands = {}, []

    if {"erc"} & set(selected):
        record, report = cli.erc(files[1], output / "erc.json")
        commands.append(record)
        s = summarize_erc(report)
        if not s["valid"]:
            results["erc"] = _result([{"error": "ERC report missing or invalid", "stderr": record["stderr"][-2000:]}], "ERROR")
        else:
            results["erc"] = _result(s["active"], excluded=s["excluded"])
    if {"drc", "schematic_parity"} & set(selected):
        record, report = cli.drc(files[2], output / "drc.json", parity="schematic_parity" in selected)
        commands.append(record)
        s = summarize_drc(report)
        if not s["valid"]:
            err = _result([{"error": "DRC report missing or invalid", "stderr": record["stderr"][-2000:]}], "ERROR")
            results.update({g: err for g in ("drc", "schematic_parity") if g in selected})
        else:
            if "drc" in selected:
                results["drc"] = _result(s["violations"] + s["unconnected_items"], excluded=s["excluded"],
                                         unconnected=len(s["unconnected_items"]))
            if "schematic_parity" in selected:
                results["schematic_parity"] = _result(s["schematic_parity"])
    if "portability" in selected:
        from tools.kicad import portability

        try:
            results["portability"] = _result(portability.check(root))
        except (KitError, sexpr.ParseError, OSError) as exc:
            results["portability"] = _result([{"error": str(exc)}], "ERROR")
    needs_model = {"library_references", "footprint_assignment", "pin_pad_mapping", "component_metadata",
                   "models_3d", "bom"}
    if needs_model & set(selected):
        try:
            model = design.schematic_symbols(files[1])
            footprints = design.board_footprints(files[2])
        except KitError as exc:
            err = _result([{"error": str(exc)}], "ERROR")
            results.update({g: err for g in needs_model & set(selected)})
        else:
            tables = LibraryTables(root)
            if "library_references" in selected:
                results["library_references"] = gate_library_references(model, footprints, tables)
            if "footprint_assignment" in selected:
                results["footprint_assignment"] = gate_footprint_assignment(model)
            if "pin_pad_mapping" in selected:
                from tools.kicad import associations

                findings, checked = associations.check(model, tables)
                results["pin_pad_mapping"] = _result(findings, checked=checked)
            if "component_metadata" in selected:
                results["component_metadata"] = gate_component_metadata(model, config["metadata_fields"])
            if "models_3d" in selected:
                results["models_3d"] = gate_models_3d(footprints, tables.variables)
            if "bom" in selected:
                results["bom"] = gate_bom(root, model, config["manufacturer_field"], config["mpn_field"])
    if "firmware" in selected:
        from tools.quality.firmware import build

        try:
            fw = build(root, "host")
            results["firmware"] = _result([] if fw["status"] == "PASS" else [{"error": "host build/tests failed"}],
                                          fw["status"], report=fw)
        except KitError as exc:
            results["firmware"] = _result([{"error": str(exc)}], "ERROR")

    if "thermal" in selected:
        from tools.thermal.analysis import analyze

        try:
            th = analyze(root, output=output / "thermal")
            results["thermal"] = _result([{"finding": f} for f in th["findings"]], th["status"], estimate=True,
                                         max_top_c=th["summary"]["max_top_c"],
                                         max_bottom_c=th["summary"]["max_bottom_c"],
                                         report=str(output / "thermal/thermal_report.html"))
        except KitError as exc:
            results["thermal"] = _result([{"error": str(exc)}], "ERROR")

    after = source_hashes(root)
    for gate in results:
        results[gate]["severity"] = severity[gate]
    blocking = [g for g, r in results.items() if r["severity"] == "required" and r["status"] != "PASS"]
    warnings = [g for g, r in results.items() if r["severity"] == "advisory" and r["status"] != "PASS"]
    unchanged = before == after
    if not unchanged:
        blocking.append("source_changed_during_verification")
    result = {
        "schema": 2,
        "at": now(),
        "project": str(root),
        "kicad_version": cli.version,
        "kicad_version_status": getattr(cli, "version_status", "TESTED"),
        "version_command": cli.version_record,
        "release_mode": release,
        "commands": commands,
        "gates": results,
        "blocking": blocking,
        "warnings": warnings,
        "source_hashes": before,
        "source_unchanged": unchanged,
        "quality_gate": "PASS" if not blocking else "FAIL",
        "fabrication_approval": False,
        "disclaimer": "Tooling checks only; not proof of electrical, thermal or fabrication readiness.",
        "report_directory": str(output),
    }
    write_json(output / "verification.json", result)
    return result


def summary_lines(result):
    lines = ["Quality gate: %s  (KiCad %s%s)" % (result["quality_gate"], result["kicad_version"],
                                                 "" if result.get("kicad_version_status", "TESTED") == "TESTED"
                                                 else ", UNTESTED VERSION")]
    for gate, r in result["gates"].items():
        line = "  %-22s %-6s %-9s %d finding(s)" % (gate, r["status"], r["severity"], r["count"])
        if r["status"] != "PASS":
            kinds = []
            for f in r["findings"]:
                label = f.get("type") or f.get("problem") or f.get("error") or f.get("finding")
                if label and label not in kinds:
                    kinds.append(str(label))
            line += ": " + ", ".join(kinds[:3]) + (" ..." if len(kinds) > 3 else "") if kinds else ""
        lines.append(line)
    if result["blocking"]:
        lines.append("Blocking: " + ", ".join(result["blocking"]))
    if any(f.get("type") == "invalid_outline" for f in result["gates"].get("drc", {}).get("findings", [])):
        lines.append("Hint: the board has no closed outline yet - draw one on Edge.Cuts in the PCB Editor.")
    lines.append("Reports: " + result["report_directory"])
    return lines
