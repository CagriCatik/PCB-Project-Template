"""Machine-global plugin discovery, verification, update checks and guided setup.

KiCad's Plugin and Content Manager (PCM) owns PCM packages; this module never
edits its database or package folders. Installation status is derived from the
PCM database plus the package payload; "VERIFIED" is only reported after the
plugin was actually invoked headlessly in this run.
"""

import configparser
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
import urllib.request
import zipfile

from tools.core import kicad_env
from tools.core.common import KitError, clean_output, now, run, sha256, write_json

CATALOG_FILE = Path(__file__).with_name("catalog.json")
CATALOG = json.loads(CATALOG_FILE.read_text())
PLUGINS = CATALOG["plugins"]
FIXTURE = kicad_env.KIT_ROOT / "qa/fixtures/divider"


def pcm_folder(identifier):
    return kicad_env.documents_dir() / "3rdparty/plugins" / identifier.replace(".", "_")


def pcm_database():
    """Authoritative KiCad 10 PCM database lives in the versioned config dir."""
    primary = kicad_env.config_dir() / "installed_packages.json"
    legacy = kicad_env.documents_dir() / "3rdparty/installed_packages.json"
    notes = []
    path = primary if primary.is_file() else (legacy if legacy.is_file() else None)
    if path is legacy:
        notes.append("Using legacy PCM database location; KiCad 10 normally writes %s" % primary)
    elif path is primary and legacy.is_file():
        notes.append("Stale legacy PCM database also present (ignored): %s" % legacy)
    data = {"packages": []}
    if path:
        try:
            data = json.loads(path.read_text())
        except ValueError:
            notes.append("PCM database is not valid JSON: %s" % path)
    packages = {p.get("package", {}).get("identifier"): p for p in data.get("packages", [])}
    return {"path": str(path) if path else None, "packages": packages, "notes": notes}


def java_major(executable="java"):
    record = run([executable, "-version"], timeout=30)
    m = re.search(r'version "(\d+)(?:\.(\d+))?', record["stderr"] + record["stdout"])
    if record["exit_code"] or not m:
        return None, record
    major = int(m.group(1))
    if major == 1 and m.group(2):  # legacy "1.8" numbering
        major = int(m.group(2))
    return major, record


def _bundled_import(module):
    python = kicad_env.bundled_python()
    if not python:
        return None
    record = run([python, "-c", "import %s as m; print(getattr(m, '__version__', 'unknown'))" % module], timeout=60)
    return record["stdout"].strip().splitlines()[-1] if record["exit_code"] == 0 and record["stdout"].strip() else None


def status(name, db=None):
    """Static installation status (no invocation)."""
    entry = PLUGINS[name]
    db = db or pcm_database()
    result = {"name": entry["name"], "key": name, "tier": entry["tier"], "install_method": entry["install"],
              "purpose": entry.get("purpose"), "optional_dependencies": entry.get("optional_dependencies", []),
              "known_limitations": entry.get("known_limitations", []),
              "kicad10_compatibility": entry["kicad10"], "homepage": entry["homepage"]}
    ident = entry.get("pcm_identifier")
    if ident:
        package = db["packages"].get(ident)
        folder = pcm_folder(ident)
        result.update({"pcm_identifier": ident, "pcm_version": package.get("current_version") if package else None,
                       "pcm_folder": str(folder), "pcm_payload_present": folder.is_dir()})
        manual = kicad_env.documents_dir() / "scripting/plugins"
        result["manual_install"] = any((manual / n).exists() for n in (ident.replace(".", "_"), entry["name"]))
    if entry.get("pip_package"):
        result["python_package_version"] = _bundled_import(entry["pip_package"])
    installed = bool(result.get("pcm_version") and result.get("pcm_payload_present")) or result.get("manual_install")
    if entry["install"] == "pip":
        installed = bool(result.get("python_package_version"))
    if entry["install"] == "pcm+pip" and installed and not result.get("python_package_version"):
        result["status"] = "SHIM_ONLY"
    else:
        result["status"] = "INSTALLED_UNVERIFIED" if installed else "NOT_INSTALLED"
    return result


# -- headless verification ----------------------------------------------------
def _fixture_copy(tmp):
    target = Path(tmp) / "fixture board"
    shutil.copytree(FIXTURE, target)
    return target / "divider.kicad_pcb"


def ibom_script():
    for base in (pcm_folder(PLUGINS["interactivehtmlbom"]["pcm_identifier"]),
                 kicad_env.documents_dir() / "scripting/plugins/InteractiveHtmlBom"):
        script = base / "generate_interactive_bom.py"
        if script.is_file():
            return script
    return None


def run_ibom(pcb, outdir, name="ibom"):
    """Generate an InteractiveHtmlBom page headlessly with KiCad's Python."""
    script, python = ibom_script(), kicad_env.bundled_python()
    if not script or not python:
        return {"status": "SKIPPED", "reason": "InteractiveHtmlBom or KiCad bundled Python not installed"}
    outdir = Path(outdir)
    record = run([python, script, "--no-browser", "--dest-dir", outdir, "--name-format", name, pcb],
                 timeout=300, env={"INTERACTIVE_HTML_BOM_NO_DISPLAY": "1"})
    html = outdir / (name + ".html")
    ok = record["exit_code"] == 0 and html.is_file() and html.stat().st_size > 0
    return {"status": "COMPLETE" if ok else "FAILED", "record": record, "file": str(html) if ok else None}


def freerouting_jar():
    folder = pcm_folder(PLUGINS["freerouting"]["pcm_identifier"])
    ini = folder / "plugin.ini"
    if ini.is_file():
        parser = configparser.ConfigParser()
        parser.read(ini)
        location = parser.get("artifact", "location", fallback="")
        if location and (folder / location).is_file():
            return folder / location
    jars = sorted(folder.glob("jar/freerouting-*.jar"))
    return jars[-1] if jars else None


_DSN = """import pcbnew, sys
board = pcbnew.LoadBoard(sys.argv[1])
for t in list(board.GetTracks()):
    board.Remove(t)  # route from scratch so the router has real work
assert pcbnew.ExportSpecctraDSN(board, sys.argv[2])
"""


def verify_freerouting(tmp):
    jar, python = freerouting_jar(), kicad_env.bundled_python()
    if not jar:
        return {"verified": False, "reason": "Freerouting jar not found in PCM payload"}
    major, java = java_major()
    need = PLUGINS["freerouting"]["java_min_major"]
    if major is None or major < need:
        return {"verified": False, "reason": "Java %s+ required (found %s)" % (need, major), "java": java}
    pcb = _fixture_copy(tmp)
    dsn, ses = pcb.with_suffix(".dsn"), pcb.with_suffix(".ses")
    export = run([python, "-c", _DSN, pcb, dsn], timeout=120)
    if export["exit_code"] or not dsn.is_file():
        return {"verified": False, "reason": "Specctra DSN export failed", "record": export}
    route = run(["java", "-jar", jar, "-de", dsn, "-do", ses, "-mp", "5", "--gui.enabled=false",
                 "--api_server.enabled=false", "--mcp_server.enabled=false",
                 "--logging.file.location=" + str(Path(tmp) / "freerouting-logs")], timeout=300)
    text = ses.read_text() if ses.is_file() else ""
    ok = route["exit_code"] == 0 and "(routes" in text and "(wire" in text
    return {"verified": ok, "java_major": major, "jar": str(jar), "record": route,
            "evidence": "SES with routed wires produced" if ok else "no routed SES produced"}


def verify(name):
    """Invoke the plugin headlessly on the kit fixture where that is possible."""
    entry = PLUGINS[name]
    base = status(name)
    method = entry["verify"]
    with tempfile.TemporaryDirectory(prefix="plugin-verify-") as tmp:
        if base["status"] == "NOT_INSTALLED":
            check = {"verified": False, "reason": "not installed"}
        elif method == "ibom-headless":
            r = run_ibom(_fixture_copy(tmp), Path(tmp) / "out")
            check = {"verified": r["status"] == "COMPLETE", "record": r.get("record"),
                     "evidence": "HTML BOM generated from fixture" if r["status"] == "COMPLETE" else r.get("reason")}
        elif method == "freerouting-headless":
            check = verify_freerouting(tmp)
        elif method == "kikit-panelize":
            pcb = _fixture_copy(tmp)
            (Path(tmp) / "panel").mkdir()
            out = Path(tmp) / "panel/panel.kicad_pcb"
            record = run([kicad_env.bundled_python(), "-m", "kikit.ui", "panelize", "--layout",
                          "grid; rows: 2; cols: 2; space: 2mm", "--tabs", "fixed; width: 3mm", "--cuts",
                          "mousebites", pcb, out], timeout=300)
            ok = record["exit_code"] == 0 and out.is_file()
            check = {"verified": ok, "record": record, "evidence": "2x2 panel produced" if ok else "panelize failed"}
        elif method == "kibot-version":
            record = run([kicad_env.bundled_python(), "-m", "kibot", "--version"], timeout=120)
            check = {"verified": record["exit_code"] == 0, "record": record}
        else:
            check = {"verified": False, "reason": "GUI action plugin; verify manually in PCB Editor"}
    if base["status"] != "NOT_INSTALLED":
        base["status"] = "VERIFIED" if check["verified"] else (
            "MANUAL_VERIFICATION_REQUIRED" if method == "gui-only" else "VERIFICATION_FAILED")
    for record in (check.get("record"),):
        if isinstance(record, dict) and "stderr" in record:
            record["stderr"] = clean_output(record["stderr"])[-4000:]
            record["stdout"] = clean_output(record["stdout"])[-4000:]
    base["verification"] = check
    return base


def diagnose(verify_plugins=False, report=True):
    db = pcm_database()
    plugins = [verify(n) if verify_plugins else status(n, db) for n in PLUGINS]
    major, _ = java_major()
    result = {
        "at": now(),
        "pcm_database": db["path"],
        "notes": db["notes"],
        "documents_dir": str(kicad_env.documents_dir()),
        "java_major": major,
        "verified": verify_plugins,
        "plugins": plugins,
        "required_ready": all(p["status"] in (("VERIFIED",) if verify_plugins else ("VERIFIED", "INSTALLED_UNVERIFIED"))
                              for p in plugins if p["tier"] == "required"),
    }
    if report:
        write_json(kicad_env.kit_home() / "reports/plugins.json", result)
    return result


# -- updates ------------------------------------------------------------------
def _fetch(url, timeout=30):
    # The repository rejects urllib's default agent; identify the kit honestly.
    request = urllib.request.Request(url, headers={"User-Agent": "PCB-Project-Template plugin-update-check"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec: fixed https URLs
        return response.read()


def _ver(text):
    """Numeric version padded to three parts, so "10" == "10.0" == "10.0.0"."""
    parts = [int(x) for x in re.findall(r"\d+", str(text))[:3]]
    return tuple(parts + [0] * (3 - len(parts)))


def latest_compatible(package, series=kicad_env.KICAD_SERIES, platform="macos"):
    best = None
    for v in package.get("versions", []):
        if v.get("status", "stable") != "stable":
            continue
        if v.get("platforms") and platform not in v["platforms"]:
            continue
        low, high = _ver(v.get("kicad_version", "0")), v.get("kicad_version_max")
        if low[:2] > _ver(series)[:2] or (high and _ver(high)[:2] < _ver(series)[:2]):
            continue
        if best is None or _ver(v["version"]) > _ver(best["version"]):
            best = v
    return best


def check_updates(fetch=_fetch):
    """Compare installed PCM versions with the official repository (integrity-checked)."""
    try:
        repo = json.loads(fetch(CATALOG["pcm_repository"]))
        if not str(repo["packages"]["url"]).startswith("https://"):
            raise KitError("PCM package index URL is not https: %r" % repo["packages"]["url"])
        raw = fetch(repo["packages"]["url"])
        if hashlib.sha256(raw).hexdigest() != repo["packages"]["sha256"]:
            raise KitError("PCM package index SHA-256 does not match repository.json")
        index = {p["identifier"]: p for p in json.loads(raw)["packages"]}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "UNAVAILABLE", "error": "%s: %s" % (type(exc).__name__, exc)}
    db = pcm_database()
    rows = []
    for name, entry in PLUGINS.items():
        ident = entry.get("pcm_identifier")
        if not ident:
            rows.append({"name": entry["name"], "status": "NOT_PCM", "note": "check %s" % entry["homepage"]})
            continue
        installed = (db["packages"].get(ident) or {}).get("current_version")
        latest = latest_compatible(index.get(ident, {}))
        row = {"name": entry["name"], "installed": installed, "latest_compatible": latest and latest["version"]}
        if not latest:
            row["status"] = "NO_COMPATIBLE_RELEASE"
        elif not installed:
            row["status"] = "NOT_INSTALLED"
        else:
            row["status"] = "UPDATE_AVAILABLE" if _ver(latest["version"]) > _ver(installed) else "UP_TO_DATE"
        rows.append(row)
    return {"status": "OK", "repository_updated": repo["packages"].get("update_time_utc"), "plugins": rows}


def guide(name):
    entry = PLUGINS[name]
    steps = []
    if "pcm" in entry["install"]:
        steps += [
            "Open KiCad %s > Plugin and Content Manager." % kicad_env.KICAD_VERSION,
            "Search for '%s' (identifier %s) and click Install, then Apply Pending Changes."
            % (entry["name"], entry["pcm_identifier"]),
        ]
    if entry.get("pip_package"):
        python = kicad_env.bundled_python() or "<KiCad.app>/Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
        steps.append("Install the Python package into KiCad's bundled interpreter (modifies the KiCad app bundle "
                     "or your user site; review first): '%s' -m pip install --user %s" % (python, entry["pip_package"]))
    if name == "freerouting":
        steps.append("Install a Java runtime >= %d (e.g. Eclipse Temurin); the PCM package states 'needs Java JRE 25'."
                     % entry["java_min_major"])
    steps += ["Restart the PCB Editor.", "Run: scripts/kit plugins verify %s" % name]
    return {"name": entry["name"], "purpose": entry.get("purpose"), "homepage": entry["homepage"],
            "known_limitations": entry.get("known_limitations", []), "steps": steps}


# -- optional manual installers (offline / non-PCM) ---------------------------
def install_ibom(dest=None, source=None):
    """Link a pinned InteractiveHtmlBom checkout into the scripting plugin path.

    Refuses to act when PCM already manages the plugin or anything differs.
    """
    entry = PLUGINS["interactivehtmlbom"]
    dest = Path(dest).expanduser() if dest else kicad_env.documents_dir() / "scripting/plugins"
    source = Path(source).expanduser() if source else kicad_env.kit_home() / "InteractiveHtmlBom"
    dest, source = dest.absolute(), source.absolute()
    pcm = pcm_folder(entry["pcm_identifier"])
    if pcm.exists():
        return {"status": "PCM_MANAGED", "path": str(pcm)}
    link, expected = dest / "InteractiveHtmlBom", source / "InteractiveHtmlBom"
    if (link.exists() or link.is_symlink()) and (not link.is_symlink() or os.readlink(link) != str(expected)):
        raise KitError("Existing plugin path was preserved: " + str(link))
    repo, tag = entry["manual_repository"], entry["manual_tag"]

    def git(*args):
        record = run(["git", "-C", source, *args])
        if record["exit_code"]:
            raise KitError(record["stderr"])
        return record["stdout"].strip()

    if source.is_symlink():
        raise KitError("Existing source symlink was preserved; choose a normal checkout directory.")
    if source.exists():
        if git("remote", "get-url", "origin") != repo:
            raise KitError("Existing repository origin differs.")
        if git("rev-parse", "HEAD") != git("rev-parse", tag + "^{commit}") or git("status", "--porcelain"):
            raise KitError("Existing checkout differs from the pinned clean tag; preserved unchanged.")
    else:
        source.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=source.parent, prefix=".ibom-") as tmp:
            checkout = Path(tmp) / "repo"
            record = run(["git", "clone", "--depth", "1", "--branch", tag, "--", repo, checkout], timeout=300)
            if record["exit_code"]:
                raise KitError(record["stderr"])
            checkout.rename(source)
    if not (expected / "__init__.py").is_file():
        raise KitError("Plugin entry point missing.")
    dest.mkdir(parents=True, exist_ok=True)
    if not link.is_symlink():
        link.symlink_to(expected, target_is_directory=True)
    return {"status": "INSTALLED", "version": tag, "commit": git("rev-parse", "HEAD"), "path": str(link)}


def install_archive(name, archive, digest, root=None):
    """Install the legacy action-plugin payload of a reviewed PCM ZIP manually.

    Packages with extra runtime/library payloads or IPC registration need PCM.
    """
    if name not in PLUGINS or not PLUGINS[name].get("pcm_identifier"):
        raise KitError("Unknown PCM plugin: %s" % name)
    archive = Path(archive)
    root = Path(root) if root else kicad_env.documents_dir()
    if len(digest) != 64 or sha256(archive) != digest.lower():
        raise KitError("Archive SHA-256 mismatch.")
    ident = PLUGINS[name]["pcm_identifier"]
    folder = ident.replace(".", "_")
    pcm = root / "3rdparty/plugins" / folder
    if pcm.exists():
        return {"status": "PCM_MANAGED", "path": str(pcm)}
    target = root / "scripting/plugins" / folder
    with zipfile.ZipFile(archive) as z:
        names = set()
        if sum(i.file_size for i in z.infolist()) > 500_000_000:
            raise KitError("Package is too large.")
        for info in z.infolist():
            path = PurePosixPath(info.filename)
            if path.is_absolute() or ".." in path.parts or "\\" in info.filename or stat.S_ISLNK(info.external_attr >> 16):
                raise KitError("Unsafe archive entry: " + info.filename)
            if info.filename in names:
                raise KitError("Duplicate archive entry.")
            names.add(info.filename)
            if path.parts and path.parts[0] not in ("plugins", "resources", "metadata.json"):
                raise KitError("Package has extra payloads; install it through PCM instead.")
        metadata = json.loads(z.read("metadata.json"))
        if metadata.get("identifier") != ident or metadata.get("type") != "plugin":
            raise KitError("Package identity/type mismatch.")
        compatible = [v for v in metadata.get("versions", []) if latest_compatible({"versions": [v]})]
        if len(compatible) != 1:
            raise KitError("Expected one package version compatible with KiCad 10; use PCM for multi-version packages.")
        if "plugins/__init__.py" not in names:
            raise KitError("No legacy action-plugin entry point; install IPC plugins via PCM.")
        if target.exists() or target.is_symlink():
            marker = target / ".kit-package.json"
            if marker.is_file() and json.loads(marker.read_text()).get("archive_sha256") == digest.lower():
                saved = json.loads(marker.read_text()).get("files", {})
                if all((target / p).is_file() and sha256(target / p) == h for p, h in saved.items()):
                    return {"status": "ALREADY_INSTALLED", "path": str(target)}
            raise KitError("Existing plugin differs; preserved unchanged.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent, prefix=".plugin-") as tmp:
            stage = Path(tmp) / folder
            stage.mkdir()
            for info in z.infolist():
                path = PurePosixPath(info.filename)
                if not path.parts or path.parts[0] != "plugins" or info.is_dir():
                    continue
                output = stage / Path(*path.parts[1:])
                output.parent.mkdir(parents=True, exist_ok=True)
                output.write_bytes(z.read(info))
            manifest = {p.relative_to(stage).as_posix(): sha256(p) for p in stage.rglob("*") if p.is_file()}
            write_json(stage / ".kit-package.json", {"identifier": ident, "version": compatible[0]["version"],
                                                     "archive_sha256": digest.lower(), "files": manifest})
            if target.exists():
                raise KitError("Plugin destination appeared.")
            stage.rename(target)
    return {"status": "INSTALLED", "path": str(target), "version": compatible[0]["version"]}
