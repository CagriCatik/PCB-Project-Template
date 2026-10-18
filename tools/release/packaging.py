"""Distributable source ZIP of the kit (policy files included, no generated output)."""

from pathlib import Path
import zipfile

from tools.core.common import KitError, sha256
from tools.core.common import SKIP_NAMES, SKIP_SUFFIXES


def source_files(root):
    root = Path(root).resolve()
    files = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if any(part in SKIP_NAMES or part.endswith("-backups") for part in rel.parts):
            continue
        if path.is_symlink():
            raise KitError("Source contains a symlink: %s" % rel)
        if path.is_file() and not path.name.endswith(SKIP_SUFFIXES) and not path.name.startswith("~"):
            files.append(path)
    return files


def package(root, output):
    root = Path(root).resolve()
    output = Path(output).expanduser().resolve()
    if root == output or root in output.parents:
        raise KitError("ZIP must be outside the repository to prevent recursive packaging.")
    if output.exists():
        raise KitError("Output exists; refusing to overwrite.")
    files = source_files(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for p in files:
            z.write(p, "PCB-Project-Template/" + p.relative_to(root).as_posix())
    return {"archive": str(output), "sha256": sha256(output), "files": len(files)}
