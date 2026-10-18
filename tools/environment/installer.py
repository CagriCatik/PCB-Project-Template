"""One-time, idempotent environment installation and read-only diagnostics.

Every step reports PASS / CHANGED / UNCHANGED / WARN / FAIL / SKIPPED. Re-running
changes nothing that is already in place and never replaces foreign files.
System-wide configuration is never touched; writes are limited to the repo
``.venv``, KiCad's *user* template directory and the kit's own state folder.
"""

import hashlib
import json
import platform
from pathlib import Path
import shutil
import sys
import venv

from tools import __version__ as KIT_VERSION
from tools.core import kicad_env
from tools.core.common import KitError, now, run, write_json

ROOT = kicad_env.KIT_ROOT
VENV = ROOT / ".venv"
REQUIREMENTS = (ROOT / "requirements.txt",)


def _step(name, status, detail=None, **extra):
    return {"step": name, "status": status, "detail": detail, **extra}


def check_platform():
    system, machine = platform.system(), platform.machine()
    detail = "%s %s (%s)" % (system, platform.mac_ver()[0] if system == "Darwin" else platform.release(), machine)
    if system != "Darwin":
        return _step("platform", "WARN", detail + "; only macOS is supported by the installer")
    return _step("platform", "PASS", detail)


def check_kicad():
    from tools.kicad.cli import KiCadCLI

    app = kicad_env.kicad_app()
    try:
        cli = KiCadCLI()
    except KitError as exc:
        return _step("kicad", "FAIL", str(exc), app=str(app) if app else None), None
    caps = cli.capabilities()
    return _step("kicad", "PASS", "KiCad %s" % cli.version, app=str(app), cli=cli.executable,
                 bundled_python=str(kicad_env.bundled_python()), cli_commands=len(caps)), cli


def check_tools():
    found = {"python": {"path": sys.executable, "version": platform.python_version()}}
    git = run(["git", "--version"])
    found["git"] = git["stdout"].strip() if git["exit_code"] == 0 else None
    code = shutil.which("code")
    app = next((p for p in (Path("/Applications/Visual Studio Code.app"),
                            Path.home() / "Applications/Visual Studio Code.app") if p.is_dir()), None)
    found["vscode"] = code or (str(app) if app else None)
    from tools.plugins.manager import java_major
    from tools.quality.firmware import toolchains

    found["java_major"] = java_major()[0]
    found["firmware_toolchains"] = toolchains()
    from tools.quality.firmware import stm32_environment

    found["stm32"] = stm32_environment()  # optional; PCB-only work never needs it
    status = "PASS" if sys.version_info >= (3, 10) and found["git"] else "FAIL"
    missing = [k for k in ("git", "vscode") if not found[k]]
    detail = "missing optional: " + ", ".join(missing) if missing else "Python, Git and VS Code found"
    if sys.version_info < (3, 10):
        detail = "Python >= 3.10 required (running %s)" % platform.python_version()
    return _step("tools", status if status == "FAIL" else ("WARN" if missing else "PASS"), detail, tools=found)


def _requirements_digest():
    h = hashlib.sha256()
    for path in REQUIREMENTS:
        h.update(path.read_bytes())
    return h.hexdigest()


def venv_up_to_date():
    """True when .venv matches requirements.txt and its packages import (read-only)."""
    python, stamp = VENV / "bin/python", VENV / ".kit-requirements.sha256"
    if not (python.is_file() and stamp.is_file() and stamp.read_text().strip() == _requirements_digest()):
        return False
    return run([python, "-c", "import kipy, numpy, scipy"], timeout=60)["exit_code"] == 0


def setup_venv(skip=False):
    if skip:
        return _step("python_venv", "SKIPPED", "--skip-venv given")
    python = VENV / "bin/python"
    stamp = VENV / ".kit-requirements.sha256"
    digest = _requirements_digest()
    if venv_up_to_date():
        return _step("python_venv", "UNCHANGED", str(VENV))
    created = not python.is_file()
    if created:
        venv.EnvBuilder(with_pip=True).create(VENV)
    record = run([python, "-m", "pip", "install", "--disable-pip-version-check", "-r", ROOT / "requirements.txt"],
                 timeout=900)
    if record["exit_code"]:
        return _step("python_venv", "FAIL", "pip install failed (network?): " + record["stderr"][-1500:])
    stamp.write_text(digest + "\n")
    return _step("python_venv", "CHANGED", ("created " if created else "updated ") + str(VENV))


def install_templates(dest=None, update=False):
    from tools.project import templates as template_engine

    try:
        result = template_engine.install_native(dest, update=update)
    except (KitError, OSError) as exc:
        return _step("kicad_templates", "FAIL", str(exc))
    actions = {r["action"] for r in result["results"]}
    if actions & {"SKIPPED_FOREIGN", "SKIPPED_MODIFIED", "UPDATE_AVAILABLE"}:
        status = "WARN"
    elif actions & {"INSTALLED", "UPDATED"}:
        status = "CHANGED"
    else:
        status = "UNCHANGED"
    return _step("kicad_templates", status, result["template_dir"], results=result["results"])


def check_plugins(verify=True):
    from tools.plugins import manager as plugins

    try:
        result = plugins.diagnose(verify_plugins=verify)
    except (KitError, OSError) as exc:
        return _step("plugins", "FAIL", str(exc))
    guides = [plugins.guide(p["key"]) for p in result["plugins"]
              if p["status"] not in ("VERIFIED", "INSTALLED_UNVERIFIED", "MANUAL_VERIFICATION_REQUIRED")]
    status = "PASS" if result["required_ready"] else "WARN"
    rows = [{k: p.get(k) for k in ("name", "tier", "status", "pcm_version", "python_package_version")}
            for p in result["plugins"]]
    return _step("plugins", status, "required plugins ready" if result["required_ready"]
                 else "a required plugin is missing or failed verification", plugins=rows,
                 guided_setup=guides, notes=result["notes"])


def check_libraries():
    from tools.kicad.libraries import LibraryTables

    summary = LibraryTables().summary()
    broken = sum(len(summary[k]["broken"]) for k in ("symbol", "footprint"))
    counts = {k: summary[k]["libraries"] for k in ("symbol", "footprint")}
    if summary["problems"] or broken or not all(counts.values()):
        return _step("library_paths", "FAIL", "; ".join(summary["problems"]) or "%d broken libraries" % broken,
                     **summary)
    return _step("library_paths", "PASS", "%(symbol)d symbol / %(footprint)d footprint libraries resolve" % counts,
                 path_vars={k: v for k, v in kicad_env.path_vars().items() if k.startswith("KICAD10")})


def check_ipc():
    from tools.kicad import ipc

    result = ipc.save_report(ipc.diagnose())
    return _step("ipc", "PASS" if result["reachable"] else "WARN", result["status"], causes=result["causes"],
                 api_enable_server=result["config"]["enable_server"], client_python=result["client_python"])


def install(skip_venv=False, template_dir=None, update_templates=False, verify_plugins=True, report_path=None):
    steps = [check_platform()]
    kicad_step, _cli = check_kicad()
    steps.append(kicad_step)
    steps.append(check_tools())
    if kicad_step["status"] == "FAIL":
        steps.append(_step("abort", "FAIL", "KiCad %s is required; see docs/INSTALLATION.md "
                           "(scripts/install-kicad.sh installs the official DMG)." % kicad_env.KICAD_VERSION))
    else:
        steps.append(setup_venv(skip_venv))
        steps.append(install_templates(template_dir, update_templates))
        steps.append(check_plugins(verify_plugins))
        steps.append(check_libraries())
        steps.append(check_ipc())
    return _report("install", steps, report_path)


def doctor(report_path=None, verify_plugins=False):
    from tools.project.templates import native_status

    steps = [check_platform()]
    kicad_step, _ = check_kicad()
    steps += [kicad_step, check_tools()]
    venv_ok = (VENV / "bin/python").is_file()
    steps.append(_step("python_venv", "PASS" if venv_ok else "WARN", str(VENV) if venv_ok else
                       "not created; run ./install_template.command"))
    if kicad_step["status"] != "FAIL":
        status = native_status()
        states = {t["state"] for t in status["templates"]}
        steps.append(_step("kicad_templates", "PASS" if states == {"INSTALLED"} else "WARN",
                           status["template_dir"], templates=status["templates"]))
        steps += [check_plugins(verify_plugins), check_libraries(), check_ipc()]
    return _report("doctor", steps, report_path)


def _report(kind, steps, report_path):
    failed = [s["step"] for s in steps if s["status"] == "FAIL"]
    report = {
        "schema": 1,
        "kind": kind,
        "at": now(),
        "kit_version": KIT_VERSION,
        "kicad_required": kicad_env.KICAD_VERSION,
        "overall": "FAIL" if failed else ("WARN" if any(s["status"] == "WARN" for s in steps) else "PASS"),
        "changed": [s["step"] for s in steps if s["status"] == "CHANGED"],
        "failed": failed,
        "steps": steps,
    }
    path = Path(report_path) if report_path else ROOT / "qa/generated/environment" / ("%s-report.json" % kind)
    write_json(path, report)
    report["report_file"] = str(path)
    return report


def report_lines(report):
    lines = ["%s: %s  (kit %s, KiCad %s required)" % (report["kind"].upper(), report["overall"],
                                                       report["kit_version"], report["kicad_required"])]
    for s in report["steps"]:
        lines.append("  [%-9s] %-16s %s" % (s["status"], s["step"], s["detail"] or ""))
        stm = (s.get("tools") or {}).get("stm32")
        if stm:
            lines.append("               - STM32 (optional): CubeMX %s, Arm GCC %s, Cube packages %s" % (
                stm["stm32cubemx"]["version"] or "not found",
                "found" if stm["arm_gnu_toolchain"]["bin"] else "not found",
                ", ".join(stm["stm32cube_packages"]["packages"]) or "none"))
        for row in s.get("plugins", []):
            lines.append("               - %-20s %-28s %s" % (row["name"], row["status"], row.get("pcm_version") or ""))
        for row in s.get("results", []) or []:
            lines.append("               - %-16s %s" % (row["template"], row["action"]))
        for cause in s.get("causes", []) or []:
            lines.append("               ! " + cause)
    lines.append("Report: " + report["report_file"])
    return lines


def report_json(report):
    return json.dumps(report, indent=2)
