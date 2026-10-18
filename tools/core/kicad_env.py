"""Single source of truth for KiCad 10 and kit locations on this machine.

Every path can be redirected with an environment variable so tests and
alternative installations never touch the real user configuration:

KICAD_APP              KiCad.app bundle
KICAD_CLI              kicad-cli executable
KICAD_CONFIG_HOME      base of the versioned config dir (default ~/Library/Preferences/kicad)
KICAD_DOCUMENTS_HOME   base of the versioned documents dir (default ~/Documents/KiCad)
KICAD_USER_TEMPLATE_DIR  user template directory
KICAD_KIT_HOME         machine-local kit state (project registry, caches)
"""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

KICAD_VERSION = "10.0.7"
KICAD_SERIES = "10.0"
KIT_ROOT = Path(__file__).resolve().parents[2]

_APP_CANDIDATES = (
    Path("/Applications/KiCad/KiCad.app"),
    Path.home() / "Applications/KiCad/KiCad.app",
)


def kicad_app():
    if os.environ.get("KICAD_APP"):
        p = Path(os.environ["KICAD_APP"]).expanduser()
        return p if p.is_dir() else None
    return next((p for p in _APP_CANDIDATES if p.is_dir()), None)


def kicad_cli_path():
    """Explicit KICAD_CLI wins, even if it is missing (so tests can force absence)."""
    if "KICAD_CLI" in os.environ:
        p = Path(os.environ["KICAD_CLI"]).expanduser()
        return p if p.is_file() else None
    app = kicad_app()
    if app and (app / "Contents/MacOS/kicad-cli").is_file():
        return app / "Contents/MacOS/kicad-cli"
    found = shutil.which("kicad-cli")
    return Path(found) if found else None


def bundled_python():
    """KiCad's own Python, the only interpreter that can import pcbnew."""
    if os.environ.get("KICAD_PCBNEW_PYTHON"):
        p = Path(os.environ["KICAD_PCBNEW_PYTHON"]).expanduser()
        return p if p.is_file() else None
    app = kicad_app()
    if not app:
        return None
    p = app / "Contents/Frameworks/Python.framework/Versions/Current/bin/python3"
    return p if p.is_file() else None


def shared_support():
    app = kicad_app()
    return app / "Contents/SharedSupport" if app else None


def config_dir():
    if os.environ.get("KICAD_CONFIG_HOME"):
        base = Path(os.environ["KICAD_CONFIG_HOME"]).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Preferences/kicad"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "kicad"
    return base / KICAD_SERIES


def documents_dir():
    if os.environ.get("KICAD_DOCUMENTS_HOME"):
        base = Path(os.environ["KICAD_DOCUMENTS_HOME"]).expanduser()
    elif sys.platform == "darwin":
        base = Path.home() / "Documents/KiCad"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "kicad"
    return base / KICAD_SERIES


def common_settings():
    """kicad_common.json content, or {} when absent/unreadable."""
    path = config_dir() / "kicad_common.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def configured_path_vars():
    """Path variables configured in KiCad Preferences > Configure Paths."""
    env = common_settings().get("environment", {}) or {}
    return dict(env.get("vars") or {})


def path_vars(project_root=None):
    """Variables KiCad 10 resolves in library tables and model paths.

    Older versioned names (e.g. KICAD9_3DMODEL_DIR) are deliberately *not*
    aliased: kicad-cli 10.0.7 does not resolve them either, and reporting them
    as unresolved is the accurate result.
    """
    support = shared_support()
    result = {}
    if support:
        result.update(
            {
                "KICAD10_SYMBOL_DIR": str(support / "symbols"),
                "KICAD10_FOOTPRINT_DIR": str(support / "footprints"),
                "KICAD10_3DMODEL_DIR": str(support / "3dmodels"),
                "KICAD10_TEMPLATE_DIR": str(support / "template"),
            }
        )
    result["KICAD10_3RD_PARTY"] = str(documents_dir() / "3rdparty")
    result["KICAD_USER_TEMPLATE_DIR"] = str(user_template_dir())
    result.update(configured_path_vars())
    for key in list(result) + [k for k in os.environ if k.startswith("KICAD")]:
        if key in os.environ and key not in ("KICAD_CLI", "KICAD_APP"):
            result[key] = os.environ[key]
    if project_root is not None:
        result["KIPRJMOD"] = str(Path(project_root).resolve())
    return result


_VAR = re.compile(r"\$\{([A-Za-z0-9_]+)\}|\$\(([A-Za-z0-9_]+)\)")


def expand(text, variables):
    """Expand ${VAR}; returns (expanded, unresolved_names)."""
    missing = []

    def sub(m):
        name = m.group(1) or m.group(2)
        if name in variables:
            return variables[name]
        missing.append(name)
        return m.group(0)

    return _VAR.sub(sub, text), missing


def user_template_dir():
    if os.environ.get("KICAD_USER_TEMPLATE_DIR"):
        return Path(os.environ["KICAD_USER_TEMPLATE_DIR"]).expanduser()
    configured = configured_path_vars().get("KICAD_USER_TEMPLATE_DIR")
    if configured:
        return Path(configured).expanduser()
    return documents_dir() / "template"


def kit_home():
    """Machine-local companion state; must stay outside any source tree."""
    if os.environ.get("KICAD_KIT_HOME"):
        path = Path(os.environ["KICAD_KIT_HOME"]).expanduser()
    elif sys.platform == "darwin":
        path = Path.home() / "Library/Application Support/PCB-Project-Template"
    else:
        path = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "PCB-Project-Template"
    path = path.resolve()
    if path == KIT_ROOT or KIT_ROOT in path.parents:
        raise ValueError("KICAD_KIT_HOME must stay outside the kit repository.")
    return path


_EDITOR = re.compile(r"/(kicad|pcbnew|eeschema)$|/(PCB Editor|Schematic Editor|KiCad)\.app/", re.I)


def running_kicad():
    """PIDs and commands of running KiCad GUI processes (excluding kicad-cli)."""
    if os.environ.get("KICAD_KIT_ASSUME_RUNNING") is not None:
        flag = os.environ["KICAD_KIT_ASSUME_RUNNING"] == "1"
        return [{"pid": 0, "command": "simulated"}] if flag else []
    try:
        out = subprocess.run(
            ["ps", "-axo", "pid=,comm="], capture_output=True, text=True, timeout=10
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    found = []
    for line in out.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) != 2:
            continue
        pid, command = parts
        if "kicad-cli" in command or "Python" in command:
            continue
        if _EDITOR.search(command) and "KiCad" in command:
            found.append({"pid": int(pid), "command": command})
    return found
