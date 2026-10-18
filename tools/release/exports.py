"""Manufacturing exports with reproducibility evidence and a fail-closed release gate.

Every export run is staged and published atomically into
``manufacturing/releases/generated/rev-<REV>-DRAFT`` (NO-GO) or ``-GO``.
A GO release requires all of:
  * explicit authorization (``authorize=True`` / ``--authorize``),
  * a signed approval file bound to the revision and exact Git commit,
  * a clean, independent Git repository for the project,
  * a passing verification run in release mode,
  * complete exports and unchanged sources.
Nothing here stages, commits or pushes.
"""

import csv
from datetime import date
import json
from pathlib import Path
import re
import shutil
import tempfile

from tools.core.common import VERSION, KitError, check_locks, git_state, now, project_files, sha256, source_hashes, write_json
from tools.kicad.cli import KiCadCLI
from tools.quality.verification import verify

GATES = (
    "requirements",
    "interfaces",
    "erc_review",
    "drc_review",
    "netlist_review",
    "power_thermal",
    "vendor_assets",
    "mechanical",
    "fabrication",
    "assembly",
    "firmware_interfaces",
    "prototype_validation",
)

BOM_FIELDS = "Reference,Value,Footprint,${QUANTITY},${DNP},Manufacturer,MPN,Datasheet"
BOM_LABELS = "Refs,Value,Footprint,Qty,DNP,Manufacturer,MPN,Datasheet"


def check_approval(path, revision, commit):
    data = json.loads(Path(path).read_text())
    if data.get("decision") != "GO" or data.get("revision") != revision or data.get("commit") != commit:
        raise KitError("Approval must say GO and bind the exact revision and Git commit.", 22)
    if not data.get("approver") or not data.get("date") or not data.get("signed_checklist"):
        raise KitError("Approver, date and signed checklist evidence are required.", 22)
    try:
        date.fromisoformat(data["date"])
    except ValueError:
        raise KitError("Approval date must be ISO YYYY-MM-DD.", 22)
    for gate in GATES:
        entry = data.get("gates", {}).get(gate, {})
        if entry.get("status") not in ("PASS", "NOT_APPLICABLE") or not entry.get("evidence"):
            raise KitError("Unresolved gate or missing evidence: " + gate, 22)
    return data


# -- reproducibility ----------------------------------------------------------
_TIMESTAMPS = [
    re.compile(rb"^%TF\.CreationDate,[^*]*\*%$", re.M),
    re.compile(rb"^G04 Created by KiCad .* date [^*]*\*$", re.M),
    re.compile(rb'"CreationDate": "[^"]*"'),
    re.compile(rb"^; DRILL file .* date .*$", re.M),
    re.compile(rb"^; #@! TF\.CreationDate,.*$", re.M),
    re.compile(rb'\(date "[^"]*"\)'),
    re.compile(rb"/(CreationDate|ModDate) \(D:[^)]*\)"),
    re.compile(rb"^## Created on .*$", re.M),
]
_STEP_ENTITY = re.compile(rb"^#\d+\s*=\s*([A-Z0-9_]+)\s*\(", re.M)


def normalized_digest(path):
    """Content hash with known export timestamps removed.

    STEP writers (OpenCascade) also renumber entities between runs, so STEP
    files get a structural fingerprint: the multiset of entity types.
    """
    data = Path(path).read_bytes()
    if Path(path).suffix.lower() in (".step", ".stp"):
        counts = {}
        for name in _STEP_ENTITY.findall(data):
            counts[name] = counts.get(name, 0) + 1
        data = b"\n".join(b"%s=%d" % (k, v) for k, v in sorted(counts.items()))
        method = "step-entity-census"
    else:
        for pattern in _TIMESTAMPS:
            data = pattern.sub(b"<timestamp>", data)
        method = "timestamps-stripped"
    import hashlib

    return {"sha256": hashlib.sha256(data).hexdigest(), "method": method}


def _artifacts(stage):
    out = {}
    for p in sorted(stage.rglob("*")):
        if p.is_file() and p.name != "manifest.json":
            rel = p.relative_to(stage).as_posix()
            out[rel] = {"sha256": sha256(p), "bytes": p.stat().st_size, "normalized": normalized_digest(p)}
    return out


# -- export plan --------------------------------------------------------------
def export_plan(stage, sch, pcb):
    """(name, cli path, args, expected outputs) for every native export."""
    fab, asm, mech, doc = stage / "fabrication", stage / "assembly", stage / "mechanical", stage / "documentation"
    return [
        ("gerbers", ("pcb", "export", "gerbers"), ["--output", str(fab / "gerbers") + "/", pcb],
         [fab / "gerbers"]),
        ("drill", ("pcb", "export", "drill"),
         ["--format", "excellon", "--excellon-units", "mm", "--generate-map", "--map-format", "pdf",
          "--output", str(fab / "drill") + "/", pcb], [fab / "drill"]),
        ("bom", ("sch", "export", "bom"),
         ["--fields", BOM_FIELDS, "--labels", BOM_LABELS, "--group-by", "Value,Footprint,Manufacturer,MPN",
          "--output", asm / "bom.csv", sch], [asm / "bom.csv"]),
        ("positions", ("pcb", "export", "pos"),
         ["--format", "csv", "--units", "mm", "--side", "both", "--exclude-dnp", "--output",
          asm / "positions.csv", pcb], [asm / "positions.csv"]),
        ("assembly_top", ("pcb", "export", "pdf"),
         ["--layers", "F.Fab,Edge.Cuts", "--mode-single", "--include-border-title", "--output",
          asm / "assembly-top.pdf", pcb], [asm / "assembly-top.pdf"]),
        ("assembly_bottom", ("pcb", "export", "pdf"),
         ["--layers", "B.Fab,Edge.Cuts", "--mode-single", "--mirror", "--include-border-title", "--output",
          asm / "assembly-bottom.pdf", pcb], [asm / "assembly-bottom.pdf"]),
        ("step", ("pcb", "export", "step"),
         ["--force", "--no-dnp", "--output", mech / "board.step", pcb], [mech / "board.step"]),
        ("schematic_pdf", ("sch", "export", "pdf"), ["--output", doc / "schematic.pdf", sch],
         [doc / "schematic.pdf"]),
        ("netlist", ("sch", "export", "netlist"),
         ["--format", "kicadsexpr", "--output", doc / "netlist.net", sch], [doc / "netlist.net"]),
    ]


def _complete(paths):
    for p in paths:
        if p.suffix:
            if not (p.is_file() and p.stat().st_size > 0):
                return False
        elif not (p.is_dir() and any(p.iterdir())):
            return False
    return True


def export_project(root, revision, approval=None, cli=None, authorize=False, ibom=True):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", revision or ""):
        raise KitError("Invalid revision identifier (letters, digits, _ . -).")
    root = Path(root).resolve()
    files = project_files(root)
    check_locks(root)
    release = approval is not None
    if release and not authorize:
        raise KitError("A GO release requires explicit authorization (--authorize).", 22)
    cli = cli or KiCadCLI()
    if release and getattr(cli, "version_status", "TESTED") != "TESTED":
        raise KitError("KiCad %s is not the tested %s; GO releases are blocked for untested versions."
                       % (cli.version, VERSION), 22)
    state = git_state(root)
    approved, references = None, []
    if release:
        if state["dirty"] or not state["commit"]:
            raise KitError("Release requires an independent clean Git repository with a commit.", 22)
        approved = check_approval(approval, revision, state["commit"])
        references = [approved["signed_checklist"]] + [v["evidence"] for v in approved["gates"].values()]
        for ref in references:
            p = (root / ref).resolve()
            if root not in p.parents or not p.is_file():
                raise KitError("Missing project-local approval evidence: " + ref, 22)
    verification = verify(root, cli, release=release)
    if release and verification["quality_gate"] != "PASS":
        raise KitError("Verification failed (%s); release blocked." % ", ".join(verification["blocking"]), 22)
    before = source_hashes(root)
    if before != verification["source_hashes"]:
        raise KitError("Source changed after verification.", 22)
    parent = root / "manufacturing/releases/generated"
    parent.mkdir(parents=True, exist_ok=True)
    target = parent / ("rev-" + revision + ("-GO" if release else "-DRAFT"))
    if target.exists():
        raise KitError("Export destination already exists; choose a new revision. Nothing overwritten.", 21)
    with tempfile.TemporaryDirectory(dir=parent, prefix=".export-") as tmp:
        stage = Path(tmp) / "release"
        for sub in ("fabrication/gerbers", "fabrication/drill", "assembly", "mechanical", "documentation"):
            (stage / sub).mkdir(parents=True)
        sch, pcb = files[1], files[2]
        records, outputs = {}, {}
        for name, path, args, expected in export_plan(stage, sch, pcb):
            records[name] = cli.command(path, args)
            outputs[name] = "COMPLETE" if records[name]["exit_code"] == 0 and _complete(expected) else "FAILED"
        if ibom:
            from tools.plugins.manager import run_ibom

            ib = run_ibom(pcb, stage / "assembly")
            records["interactive_html_bom"] = ib.get("record")
            outputs["interactive_html_bom"] = ib["status"]
        consistency = designator_consistency(stage, files)
        outputs["designator_consistency"] = "COMPLETE" if not consistency else "FAILED"
        complete = all(v == "COMPLETE" for k, v in outputs.items() if k != "interactive_html_bom")
        unchanged = before == source_hashes(root)
        if release and (not complete or not unchanged or git_state(root) != state):
            raise KitError("Exports failed or source/Git state changed; no GO release created.", 22)
        shutil.copytree(verification["report_directory"], stage / "verification")
        if release:
            shutil.copy2(approval, stage / "approval.json")
            for ref in references:
                dst = stage / "evidence" / ref
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(root / ref, dst)
        manifest = {
            "schema": 2,
            "created": now(),
            "revision": revision,
            "project": files[0].stem,
            "git": state,
            "kicad_version": cli.version,
            "kicad_version_status": getattr(cli, "version_status", "TESTED"),
            "decision": "GO" if release else "NO-GO",
            "label": "RELEASE" if release else "DRAFT - NOT FOR FABRICATION",
            "quality_gate": verification["quality_gate"],
            "blocking_gates": verification["blocking"],
            "advisory_warnings": verification["warnings"],
            "outputs": outputs,
            "designator_findings": consistency,
            "exports_complete": complete,
            "configuration": _configuration(root),
            "known_limitations": KNOWN_LIMITATIONS + ["Advisory gate not passing: " + g
                                                      for g in verification["warnings"]],
            "source_unchanged": unchanged,
            "source_hashes": before,
            "commands": records,
            "artifacts": _artifacts(stage),
            "approval": approved,
            "disclaimer": "Exports and checks are tooling results; they do not establish electrical, "
                          "thermal or fabrication readiness without review and prototype validation.",
        }
        write_json(stage / "manifest.json", manifest)
        if target.exists():
            raise KitError("Export destination appeared during export.", 21)
        stage.rename(target)
    return target, manifest


KNOWN_LIMITATIONS = [
    "Exports are generated with the project's own plot settings and the CLI options listed in 'commands'; "
    "fabricator-specific requirements (layer naming, panelization, stack-up notes) are not assumed.",
    "STEP reproducibility is compared by entity census, not byte identity.",
    "Interactive HTML BOM is optional; its absence does not block a release.",
]


def _configuration(root):
    from tools.quality.verification import load_config

    meta = root / "meta/project.json"
    return {"verification": load_config(root),
            "project": json.loads(meta.read_text()) if meta.is_file() else None}


def expand_refs(text, delimiter=","):
    """'R1,R3-R5' -> ['R1', 'R3', 'R4', 'R5'] (KiCad BOM reference ranges)."""
    refs = []
    for part in (p.strip() for p in text.split(delimiter)):
        m = re.fullmatch(r"([A-Za-z_#]+)(\d+)-\1?(\d+)", part)
        if m:
            refs += ["%s%d" % (m.group(1), n) for n in range(int(m.group(2)), int(m.group(3)) + 1)]
        elif part:
            refs.append(part)
    return refs


def designator_consistency(stage, files):
    """Designators in BOM, placement file, schematic and board must agree."""
    from tools.kicad import design

    model = design.schematic_symbols(files[1])
    board = design.board_footprints(files[2])
    findings = []
    bom_path, pos_path = stage / "assembly/bom.csv", stage / "assembly/positions.csv"
    if not bom_path.is_file() or not pos_path.is_file():
        return [{"problem": "BOM or position file missing; consistency not checked"}]
    with bom_path.open(newline="") as fp:
        bom = [r for row in csv.DictReader(fp) for r in expand_refs(row.get("Refs", ""))]
    with pos_path.open(newline="") as fp:
        pos = [row.get("Ref", "") for row in csv.DictReader(fp)]
    expected_bom = {s["reference"] for s in model["symbols"] if s["in_bom"] and not s["power"]}
    placed = {f["reference"] for f in board
              if not {"exclude_from_pos_files", "dnp"} & set(f["attributes"])}
    schematic = {s["reference"] for s in model["symbols"] if s["on_board"] and not s["power"]}
    board_refs = {f["reference"] for f in board if "board_only" not in f["attributes"]}

    def compare(label, actual, expected):
        if len(actual) != len(set(actual)):
            findings.append({"problem": "%s lists a designator twice" % label,
                             "references": sorted({r for r in actual if actual.count(r) > 1})})
        for ref in sorted(set(actual) ^ expected):
            findings.append({"problem": "%s %s" % (label, "has extra" if ref in actual else "is missing"),
                             "reference": ref})

    compare("BOM", bom, expected_bom)
    compare("position file", pos, placed)
    for ref in sorted(schematic ^ board_refs):
        findings.append({"problem": "schematic/board designator mismatch", "reference": ref})
    return findings


def release_status(root):
    """Classify existing exports: CURRENT, STALE (sources changed), MODIFIED or INCOMPLETE."""
    root = Path(root).resolve()
    project_files(root)
    parent = root / "manufacturing/releases/generated"
    current = source_hashes(root)
    rows = []
    for folder in sorted(parent.glob("rev-*")) if parent.is_dir() else []:
        manifest = folder / "manifest.json"
        row = {"release": folder.name, "path": str(folder)}
        if not manifest.is_file():
            rows.append(dict(row, status="INCOMPLETE", detail="no manifest.json"))
            continue
        data = json.loads(manifest.read_text())
        changed = sorted(k for k in set(current) | set(data["source_hashes"])
                         if current.get(k) != data["source_hashes"].get(k))
        on_disk = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {"manifest.json"}
        tampered = sorted(n for n, a in data["artifacts"].items()
                          if n not in on_disk or sha256(folder / n) != a["sha256"])
        extra = sorted(on_disk - set(data["artifacts"]))
        if tampered or extra:
            status, detail = "MODIFIED", {"changed_artifacts": tampered, "unexpected_files": extra}
        elif changed:
            status, detail = "STALE", {"changed_sources": changed}
        else:
            status, detail = "CURRENT", None
        rows.append(dict(row, status=status, decision=data.get("decision"), created=data.get("created"),
                         detail=detail))
    return rows


def compare_manifests(a, b):
    """Artifacts whose normalized digests differ between two export manifests."""
    ma, mb = (json.loads(Path(p).read_text()) for p in (a, b))
    names = sorted(set(ma["artifacts"]) | set(mb["artifacts"]))
    diff = []
    for n in names:
        if n.startswith("verification/"):
            continue  # report directories carry their own timestamps by design
        x, y = ma["artifacts"].get(n), mb["artifacts"].get(n)
        if not x or not y or x["normalized"]["sha256"] != y["normalized"]["sha256"]:
            diff.append(n)
    return {"identical": not diff, "differences": diff, "compared": len(names)}
