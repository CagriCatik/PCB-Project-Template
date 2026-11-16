"""Fresh, source-bound render/snapshot runs. No edits, Git writes or auto-approval."""
import html
import json
import math
import struct
from pathlib import Path
import shutil
import tempfile

from tools.core.common import VERSION, KitError, check_locks, now, run, sha256, write_json
from tools.kicad.cli import KiCadCLI, summarize_erc
from tools.schematic.model import SCHEMA, compare, inventory, netlist
from tools.schematic.layout import hints


def _required_cli(cli):
    cli = cli or KiCadCLI()
    if cli.version != VERSION or cli.version_status != "TESTED":
        raise KitError("Schematic evidence requires KiCad %s; untested overrides are not accepted" % VERSION, 11)
    return cli


def _checked(record, artifact):
    if record["exit_code"] or not artifact.is_file() or artifact.stat().st_size == 0:
        raise KitError("Export failed: %s\n%s" % (" ".join(record["argv"]), record["stderr"]), 21)


def _unchanged(schematic, hashes):
    native, current = inventory(schematic)
    _locks(schematic, native)
    if current != hashes:
        raise KitError("Schematic sources changed during review; discard this run", 21)


def _locks(schematic, native):
    for directory in {Path(schematic).parent / Path(s["file"]).parent for s in native["sheets"]}:
        check_locks(directory)


def snapshot(schematic, output, cli=None):
    """Export an immutable baseline. Destination must not exist."""
    schematic, output = Path(schematic).resolve(), Path(output).resolve()
    if output.exists():
        raise KitError("Snapshot already exists: %s" % output, 18)
    check_locks(schematic.parent)
    native, hashes = inventory(schematic)
    _locks(schematic, native)
    cli = _required_cli(cli)
    with tempfile.TemporaryDirectory(prefix="kit netlist ") as tmp:
        xml = Path(tmp) / "netlist.xml"
        record = cli.command(("sch", "export", "netlist"),
                             ["--format", "kicadxml", "--output", xml, schematic])
        _checked(record, xml)
        electrical = netlist(xml)
    _unchanged(schematic, hashes)
    data = {"schema": SCHEMA, "created": now(), "kicad": cli.version,
            "version_status": cli.version_status, "sources": hashes,
            "native": native, "electrical": electrical, "command": record}
    # Exclusive creation also protects a destination created after the first check.
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
        fp.write("\n")
    return data


def _png_size(path):
    with Path(path).open("rb") as fp:
        header = fp.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise KitError("Invalid PNG artifact: %s" % path, 21)
    return struct.unpack(">II", header[16:24])


def load_views(path):
    if not path:
        return []
    data = json.loads(Path(path).read_text())
    views = data.get("views") if isinstance(data, dict) else None
    if not isinstance(views, list):
        raise KitError("Views config needs a views array")
    names = set()
    for v in views:
        if not isinstance(v, dict) or not isinstance(v.get("id"), str):
            raise KitError("Every view needs an id")
        name = v["id"]
        if not name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in name) or name in names:
            raise KitError("View ids must be unique safe filenames")
        names.add(name)
        page, box = v.get("page"), v.get("box_mm")
        if type(page) is not int or page < 1 or not isinstance(box, list) or len(box) != 4:
            raise KitError("View needs page >= 1 and box_mm [x,y,width,height]")
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in box) or min(box[:2]) < 0 or min(box[2:]) <= 0:
            raise KitError("Invalid view dimensions")
    return views


def review(schematic, output_parent=None, views_path=None, baseline=None, dpi=150, cli=None, rasterizer=None):
    schematic = Path(schematic).resolve()
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise KitError("DPI must be between 72 and 600")
    views = load_views(views_path)
    check_locks(schematic.parent)
    _, hashes = inventory(schematic)
    cli = _required_cli(cli)
    rasterizer = rasterizer or shutil.which("pdftoppm")
    if not rasterizer:
        raise KitError("pdftoppm required for PNG views; install Poppler (brew install poppler / apt install poppler-utils)")
    parent = Path(output_parent).resolve() if output_parent else schematic.parent / "qa/generated/schematic-review"
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix="review-", dir=parent))
    report = {"schema": SCHEMA, "created": now(), "status": "INCOMPLETE", "directory": str(folder),
              "visual_status": "NOT_REVIEWED", "schematic": str(schematic), "kicad": cli.version, "version_status": cli.version_status,
              "dpi": dpi, "views": views, "sources": hashes, "commands": [], "artifacts": {}}
    write_json(folder / "manifest.json", report)
    try:
        current = snapshot(schematic, folder / "snapshot.json", cli)
        report["commands"].append(current["command"])
        if baseline:
            report["comparison"] = compare(json.loads(Path(baseline).read_text()), current)
        pdf = folder / "schematic.pdf"
        record = cli.command(("sch", "export", "pdf"), ["--output", pdf, schematic])
        report["commands"].append(record)
        _checked(record, pdf)
        record = run([rasterizer, "-png", "-r", str(dpi), pdf, folder / "page"], timeout=300)
        report["commands"].append(record)
        pages = sorted(folder.glob("page-*.png"))
        if record["exit_code"] or not pages or any(p.stat().st_size == 0 for p in pages):
            raise KitError("Overview rendering failed: " + record["stderr"], 21)
        page_sizes = {int(p.stem.split("-")[-1]): _png_size(p) for p in pages}
        for v in views:
            if v["page"] not in page_sizes:
                raise KitError("View %s references absent page" % v["id"])
            width, height = page_sizes[v["page"]]
            x, y, w, h = v["box_mm"]
            if (x + w) * dpi / 25.4 > width + 1 or (y + h) * dpi / 25.4 > height + 1:
                raise KitError("View %s lies outside the rendered page" % v["id"])
            # Fixed paper coordinates, 300 dpi for comparable before/after details.
            coords = [str(round(n * 300 / 25.4)) for n in v["box_mm"]]
            target = folder / ("detail-" + v["id"])
            record = run([rasterizer, "-png", "-singlefile", "-r", "300", "-f", str(v["page"]),
                          "-l", str(v["page"]), "-x", coords[0], "-y", coords[1],
                          "-W", coords[2], "-H", coords[3], pdf, target], timeout=300)
            report["commands"].append(record)
            _checked(record, target.with_suffix(".png"))
            if _png_size(target.with_suffix(".png")) != (int(coords[2]), int(coords[3])):
                raise KitError("Detail dimensions differ from requested crop", 21)
        record, erc = cli.erc(schematic, folder / "erc.json")
        report["commands"].append(record)
        summary = summarize_erc(erc)
        if not summary["valid"] or record["exit_code"] not in (0, 5):
            raise KitError("ERC execution failed or report is invalid", 21)
        report["erc"] = summary
        report["layout_hints"] = hints(schematic)
        _unchanged(schematic, hashes)
        report["status"] = "EVIDENCE_READY"
        report["commands"].append(run([rasterizer, "-v"]))
        images = sorted(folder.glob("*.png"))
        index = "<!doctype html><meta charset='utf-8'><title>Schematic review</title>"
        index += "<h1>Schematic review — visual inspection required</h1><p>CLI renders, not GUI screenshots. Read manifest.json for source hashes, ERC and comparison.</p>"
        index += "".join("<h2>%s</h2><a href='%s'><img style='width:100%%' src='%s' alt='%s'></a>" %
                         tuple(html.escape(s, quote=True) for s in (p.name, p.name, p.name, p.name)) for p in images)
        (folder / "index.html").write_text(index, encoding="utf-8")
        for p in sorted(folder.iterdir()):
            if p.is_file() and p.name != "manifest.json":
                report["artifacts"][p.name] = sha256(p)
    except Exception as exc:
        report["status"] = "FAILED"
        report["error"] = str(exc)
        raise
    finally:
        write_json(folder / "manifest.json", report)
    return report


def status(manifest_path):
    """Check an existing run against its recorded sources and artifact hashes."""
    manifest_path = Path(manifest_path).resolve()
    data = json.loads(manifest_path.read_text())
    if not isinstance(data, dict) or data.get("schema") != SCHEMA or data.get("status") != "EVIDENCE_READY":
        return {"status": "INCOMPLETE", "visual_status": "NOT_REVIEWED"}
    if data.get("kicad") != VERSION or data.get("version_status") != "TESTED":
        return {"status": "UNSUPPORTED", "visual_status": "NOT_REVIEWED"}
    if (not isinstance(data.get("schematic"), str) or not isinstance(data.get("sources"), dict)
            or not isinstance(data.get("artifacts"), dict) or not data["artifacts"]):
        raise KitError("Review manifest lacks source/artifact binding")
    changed = []
    for name, digest in data['artifacts'].items():
        path = manifest_path.parent / name
        if Path(name).name != name:
            raise KitError("Invalid artifact name in manifest")
        if not path.is_file() or sha256(path) != digest:
            changed.append(name)
    try:
        _, hashes = inventory(data['schematic'])
        current = hashes == data['sources']
    except (OSError, ValueError):
        current = False
    return {"status": "MODIFIED" if changed else "CURRENT" if current else "STALE",
            "sources_current": current, "changed_artifacts": changed,
            "visual_status": "NOT_REVIEWED"}
