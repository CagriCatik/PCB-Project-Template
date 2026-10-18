"""Safe filesystem operations, subprocess records and project discovery."""

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from datetime import datetime, timezone

from tools.core.kicad_env import KICAD_VERSION as VERSION

# Cosmetic warnings from a Homebrew fontconfig picked up by KiCad; raw output is
# kept in full records, only human summaries drop these lines.
_NOISE = re.compile(r"^(Fontconfig warning:|\d\d:\d\d:\d\d [AP]M: Debug:|.*stdpbase\.cpp.*create wxApp)")


# Never source: VCS/venv/caches, generated output, KiCad local state and backups.
SKIP_NAMES = {".git", ".venv", "__pycache__", ".DS_Store", "Thumbs.db", "generated", "build", ".pio",
              "fp-info-cache"}
SKIP_SUFFIXES = (".pyc", ".kicad_prl", ".lck", ".bak", ".bck")


def clean_output(text):
    return "\n".join(l for l in (text or "").splitlines() if not _NOISE.match(l)).strip()


class KitError(ValueError):
    def __init__(self, message, exit_code=2):
        super().__init__(message)
        self.exit_code = exit_code


def now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive temporary file, then atomic replacement of this tool's record.
    fd, name = tempfile.mkstemp(dir=path.parent, prefix="." + path.name)
    try:
        with os.fdopen(fd, "w") as fp:
            json.dump(data, fp, indent=2)
            fp.write("\n")
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def run(argv, cwd=None, timeout=120, env=None):
    started = now()
    try:
        result = subprocess.run(
            [str(a) for a in argv],
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            env=None if env is None else {**os.environ, **env},
        )
        return {
            "argv": [str(a) for a in argv],
            "started": started,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "argv": [str(a) for a in argv],
            "started": started,
            "exit_code": 127,
            "stdout": "",
            "stderr": str(exc),
        }


def git_state(root):
    root = Path(root).resolve()
    top = run(["git", "-C", root, "rev-parse", "--show-toplevel"])
    if top["exit_code"] or Path(top["stdout"].strip()).resolve() != root:
        return {
            "commit": None,
            "dirty": True,
            "status": "not an independent Git repository",
        }
    commit = run(["git", "-C", root, "rev-parse", "HEAD"])
    status = run(["git", "-C", root, "status", "--porcelain", "--untracked-files=all"])
    return {
        "commit": (
            (commit["stdout"].strip() or None) if commit["exit_code"] == 0 else None
        ),
        "dirty": bool(status["exit_code"] or status["stdout"]),
        "status": status["stdout"],
    }


def project_files(root):
    root = Path(root).resolve()
    projects = list(root.glob("*.kicad_pro"))
    if len(projects) != 1:
        raise KitError(
            "Expected exactly one root .kicad_pro; create a project first.", 12
        )
    files = [
        projects[0].with_suffix(s) for s in (".kicad_pro", ".kicad_sch", ".kicad_pcb")
    ]
    if not all(p.is_file() for p in files):
        raise KitError("Missing matching schematic or PCB.", 13)
    return files


def check_locks(root):
    """KiCad 10 writes ~<file>.lck next to files open in an editor."""
    locks = sorted(set(Path(root).glob("*.lck")) | set(Path(root).glob("~*.lck")))
    if locks:
        raise KitError(
            "Close the project before automation; lock files found: "
            + ", ".join(p.name for p in locks),
            14,
        )


def source_hashes(root):
    """Include hierarchical sheets, libraries, models, tables, settings and firmware.

    Generated output (including firmware build trees), editor state and
    backups are excluded with the same rules used for templates and packaging.
    """
    root = Path(root)
    result = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if any(x in SKIP_NAMES or x.endswith("-backups") for x in rel.parts):
            continue
        if p.is_symlink():
            raise ValueError("Source symlink is not portable: " + str(rel))
        if p.is_file() and not p.name.endswith(SKIP_SUFFIXES) and not p.name.startswith("~"):
            result[rel.as_posix()] = sha256(p)
    return result
