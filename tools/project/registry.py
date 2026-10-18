"""Machine-local index of generated projects (never copied into designs) and launchers."""

import json
from pathlib import Path
import shutil
import sys

from tools.core import kicad_env
from tools.core.common import KitError, project_files, run, write_json


def global_home():
    return kicad_env.kit_home()


def _path():
    return global_home() / "projects.json"


def _load():
    path = _path()
    if not path.exists():
        return {"schema": 1, "projects": []}
    try:
        return json.loads(path.read_text())
    except ValueError:
        raise KitError("Project registry is corrupt: %s (fix or remove it explicitly)." % path)


def register_project(root):
    data = _load()
    value = str(Path(root).resolve())
    if value not in data["projects"]:
        data["projects"].append(value)
        write_json(_path(), data)
    return data


def forget_project(root):
    data = _load()
    value = str(Path(root).expanduser().resolve())
    data["projects"] = [p for p in data["projects"] if p != value]
    write_json(_path(), data)
    return data


def list_projects():
    rows = []
    for value in _load()["projects"]:
        path = Path(value)
        row = {"path": value, "exists": path.is_dir()}
        try:
            row["project_file"] = project_files(path)[0].name
            meta = path / "meta/project.json"
            if meta.is_file():
                row["template"] = json.loads(meta.read_text()).get("template")
        except (KitError, ValueError, OSError):
            row["project_file"] = None
        rows.append(row)
    return rows


def open_project(root, vscode=False):
    root = Path(root).expanduser().resolve()
    if not root.is_dir():
        raise KitError("Project directory does not exist: %s" % root)
    if vscode:
        if shutil.which("code"):
            argv = ["code", root]
        elif sys.platform == "darwin":
            argv = ["open", "-a", "Visual Studio Code", root]
        else:
            raise KitError("VS Code command `code` is not installed.")
    else:
        pro = project_files(root)[0]
        app = kicad_env.kicad_app()
        if sys.platform == "darwin":
            argv = ["open", "-a", str(app), pro] if app else ["open", pro]
        else:
            argv = ["kicad", pro]
    record = run(argv)
    if record["exit_code"]:
        raise KitError("Launch failed: " + record["stderr"].strip())
    return record
