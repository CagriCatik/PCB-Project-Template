"""KiCad IPC API diagnostics and configuration (stdlib only).

Checks, in order: API server setting in kicad_common.json, running KiCad
processes, socket files, the kicad-python client, and a live bounded probe in
a separate interpreter. The CLI adapter never depends on any of this.
"""

import copy
import json
import os
from pathlib import Path
import shutil
import sys

from tools.core import kicad_env
from tools.core.common import KitError, now, run, write_json

SOCKET_DIR = Path("/tmp/kicad")  # KiCad 10 and kipy default on macOS/Linux


def api_config():
    path = kicad_env.config_dir() / "kicad_common.json"
    settings = kicad_env.common_settings()
    api = settings.get("api") or {}
    return {
        "config_file": str(path),
        "config_exists": path.is_file(),
        "enable_server": api.get("enable_server"),
        "interpreter_path": api.get("interpreter_path"),
    }


def socket_candidates():
    """KICAD_API_SOCKET first; then api.sock / api-<pid>.sock that KiCad creates."""
    found = []
    env = os.environ.get("KICAD_API_SOCKET")
    if env:
        found.append({"uri": env, "source": "KICAD_API_SOCKET",
                      "exists": Path(env.replace("ipc://", "")).exists() if env.startswith("ipc://") else None})
    if SOCKET_DIR.is_dir():
        for sock in sorted(SOCKET_DIR.glob("api*.sock")):
            found.append({"uri": "ipc://" + str(sock), "source": "discovered", "exists": True})
    return found


def client_python():
    """First interpreter that can import kipy: repo venv, legacy kit venv, current."""
    candidates = [
        os.environ.get("KICAD_KIT_IPC_PYTHON"),
        str(kicad_env.KIT_ROOT / ".venv/bin/python"),
        str(kicad_env.kit_home() / "venv/bin/python"),
        sys.executable,
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            record = run([candidate, "-c", "import kipy"], timeout=30)
            if record["exit_code"] == 0:
                return candidate
    return None


def probe(socket_uri=None, timeout_ms=3000, python=None, budget_s=20):
    python = python or client_python()
    if not python:
        return {"socket": socket_uri, "reachable": False, "error_class": "client_missing",
                "error": "kicad-python not installed; run ./install_template.command"}
    argv = [python, "-m", "tools.kicad.ipc_client", "--timeout-ms", str(timeout_ms)]
    if socket_uri:
        argv += ["--socket", socket_uri]
    record = run(argv, cwd=kicad_env.KIT_ROOT, timeout=budget_s)
    if record["exit_code"] == 127 and "timed out" in record["stderr"].lower():
        return {"socket": socket_uri, "reachable": False, "error_class": "timeout",
                "error": "probe exceeded %ss" % budget_s}
    try:
        return json.loads(record["stdout"].strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"socket": socket_uri, "reachable": False, "error_class": "probe_failed",
                "error": (record["stderr"] or record["stdout"])[-2000:]}


def diagnose(timeout_ms=3000):
    config = api_config()
    processes = kicad_env.running_kicad()
    sockets = socket_candidates()
    python = client_python()
    probes = []
    for candidate in sockets or [{"uri": None, "source": "kipy default"}]:
        result = probe(candidate["uri"], timeout_ms, python)
        probes.append(result)
        if result.get("reachable"):
            break
    connected = next((p for p in probes if p.get("reachable")), None)
    causes = []
    if not connected:
        if not processes:
            causes.append("KiCad is not running; the API server exists only inside a running KiCad.")
        if config["enable_server"] is not True:
            causes.append("API server disabled in %s (api.enable_server=%s). Enable it in KiCad: "
                          "Preferences > Plugins > Enable KiCad API, or close KiCad and run "
                          "'scripts/kit ipc enable --apply'." % (config["config_file"], config["enable_server"]))
        existing = [s for s in sockets if s.get("exists")]
        if processes and config["enable_server"] is True and not existing:
            causes.append("KiCad is running with the API enabled but no socket exists; restart KiCad.")
        if existing:
            causes.append("Socket file present but not answering; it may be stale from a crashed session.")
        for s in sockets:
            if s["source"] == "KICAD_API_SOCKET" and s.get("exists") is False:
                causes.append("KICAD_API_SOCKET points to a missing socket: %s" % s["uri"])
        if not python:
            causes.append("kicad-python client missing; run ./install_template.command.")
    result = {
        "at": now(),
        "status": "CONNECTED" if connected else "UNAVAILABLE",
        "reachable": bool(connected),
        "config": config,
        "kicad_processes": processes,
        "sockets": sockets,
        "client_python": python,
        "probes": probes,
        "connection": connected,
        "causes": causes,
        "cli_independent": "kicad-cli workflows do not need IPC.",
    }
    return result


def enable_server(apply=False):
    """Set api.enable_server=true in kicad_common.json, only while KiCad is closed.

    KiCad rewrites kicad_common.json on exit, so editing it while KiCad runs
    would either be lost or clobber live settings. A timestamped backup is kept.
    """
    config_file = kicad_env.config_dir() / "kicad_common.json"
    if not config_file.is_file():
        raise KitError("No KiCad configuration at %s; start KiCad once first." % config_file)
    settings = json.loads(config_file.read_text())
    if (settings.get("api") or {}).get("enable_server") is True:
        return {"status": "ALREADY_ENABLED", "config_file": str(config_file)}
    processes = kicad_env.running_kicad()
    if processes:
        raise KitError("KiCad is running (PIDs %s). Enable the API in Preferences > Plugins, or quit KiCad and "
                       "re-run this command." % ", ".join(str(p["pid"]) for p in processes), 16)
    updated = copy.deepcopy(settings)
    updated.setdefault("api", {})["enable_server"] = True
    if not apply:
        return {"status": "DRY_RUN", "config_file": str(config_file),
                "change": {"api.enable_server": [settings.get("api", {}).get("enable_server"), True]}}
    backup = config_file.with_name("kicad_common.json.kit-backup-" + now().replace(":", "")[:17])
    shutil.copy2(config_file, backup)
    tmp = config_file.with_name(".kicad_common.json.kit-tmp")
    tmp.write_text(json.dumps(updated, indent=4) + "\n")
    os.replace(tmp, config_file)
    return {"status": "ENABLED", "config_file": str(config_file), "backup": str(backup),
            "next": "Start KiCad; it creates %s/api.sock when the server starts." % SOCKET_DIR}


def save_report(result):
    write_json(kicad_env.kit_home() / "reports/ipc.json", result)
    return result
