"""Project templates: materialize, create independent projects, install into KiCad.

One implementation builds every project tree. It is used both for
``create`` (a user project) and for installing native KiCad templates into the
user template directory, so both paths produce identical layouts.

Template sources:
  meta/templates/skeleton.json        kit paths copied into every project
  meta/templates/<id>/template.json   base design, overlays, gate overrides
  meta/templates/<id>/meta/info.html  KiCad template metadata (native install)
"""

import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid
from html.parser import HTMLParser

from tools import __version__ as KIT_VERSION
from tools.core import kicad_env
from tools.core.common import SKIP_NAMES, SKIP_SUFFIXES, KitError, now, run, sha256, write_json

ROOT = kicad_env.KIT_ROOT
TEMPLATE_DIR = ROOT / "meta/templates"
NAME_RULE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _.-]{0,79}")
MARKER = "meta/kit-template.json"


class _Title(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside, self.title = False, ""

    def handle_starttag(self, tag, attrs):
        self.inside = self.inside or tag == "title"

    def handle_endtag(self, tag):
        if tag == "title":
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.title += data


def html_title(path):
    parser = _Title()
    parser.feed(Path(path).read_text(encoding="utf-8"))
    return parser.title.strip()


def templates():
    result = {}
    for manifest in sorted(TEMPLATE_DIR.glob("*/template.json")):
        data = json.loads(manifest.read_text())
        data["path"] = str(manifest.parent)
        info = manifest.parent / "meta/info.html"
        if not info.is_file() or not html_title(info):
            raise KitError("Template %s needs meta/info.html with a non-empty <title>." % data["id"])
        result[data["id"]] = data
    return result


def get_template(template_id):
    found = templates()
    if template_id not in found:
        raise KitError("Unknown template %r; choose one of: %s" % (template_id, ", ".join(found)))
    return found[template_id]


def validate_name(name):
    if not isinstance(name, str) or not NAME_RULE.fullmatch(name) or name.endswith((".", " ")):
        raise KitError("Project name must be 1-80 characters, start with a letter or digit and contain only "
                       "letters, digits, spaces, '_', '-' or '.', and must not end with '.' or a space.")
    if name.lower() in {"con", "aux", "nul", "prn"} or ".." in name:
        raise KitError("Project name %r is reserved or ambiguous." % name)
    return name


def _copy(src, dst):
    """Copy a file or tree without caches, editor state or generated output."""
    src, dst = Path(src), Path(dst)
    if src.is_symlink():
        raise KitError("Template source contains a symlink: %s" % src)
    if src.is_file():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if any(part in SKIP_NAMES or part.endswith("-backups") for part in rel.parts):
            continue
        if path.is_symlink():
            raise KitError("Template source contains a symlink: %s" % path)
        if path.is_dir() or path.name.endswith(SKIP_SUFFIXES) or path.name.startswith("~"):
            continue
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dst / rel)


def _render(text, values):
    for key, value in values.items():
        text = text.replace("{{%s}}" % key, value)
    return text


def _apply_skeleton(stage, values):
    spec = json.loads((TEMPLATE_DIR / "skeleton.json").read_text())
    for entry in spec["copy"]:
        src, dst = ROOT / entry["from"], stage / entry["to"]
        if not src.exists():
            raise KitError("Skeleton source missing: %s" % entry["from"])
        if src.is_dir():
            with tempfile.TemporaryDirectory() as tmp:
                _copy(src, Path(tmp) / "x")
                for excluded in entry.get("exclude", []):
                    shutil.rmtree(Path(tmp) / "x" / excluded, ignore_errors=True)
                if (Path(tmp) / "x").exists():
                    shutil.copytree(Path(tmp) / "x", dst, dirs_exist_ok=True)
        else:
            _copy(src, dst)
        if entry.get("render"):
            targets = [dst / p.relative_to(src) for p in src.rglob("*.md")] if src.is_dir() else [dst]
            for target in targets:
                target.write_text(_render(target.read_text(), values))
    for directory in spec["directories"]:
        (stage / directory).mkdir(exist_ok=True)


def _replace_exact(path, old, new, required=True):
    text = path.read_text(encoding="utf-8")
    if old not in text:
        if required:
            raise KitError("Expected text not found in %s: %s" % (path.name, old))
        return 0
    path.write_text(text.replace(old, new), encoding="utf-8")
    return text.count(old)


def _quote(text):
    return text.replace("\\", "\\\\").replace('"', '\\"')


TITLE_BLOCK = '\t(title_block\n\t\t(title "${PROJECTNAME}")\n\t\t(rev "A")\n\t)\n'


def _base_native_defaults(stage, name, uuid_seed=None, profile_id=None):
    from tools.project import profiles

    profile_id = profile_id or profiles.DEFAULT_PROFILE
    pro, pcb = profiles.default_files(profile_id)
    shutil.copy2(pro, stage / (name + ".kicad_pro"))
    shutil.copy2(pcb, stage / (name + ".kicad_pcb"))
    sch = stage / (name + ".kicad_sch")
    shutil.copy2(ROOT / "hardware/native-defaults/default.kicad_sch", sch)
    # A fresh root-sheet UUID keeps independently created projects distinct; an
    # installed native template uses a stable one so reinstalls are comparable.
    sheet = uuid.uuid5(uuid.NAMESPACE_URL, "pcb-project-template:" + uuid_seed) if uuid_seed else uuid.uuid4()
    text = re.sub(r"\(uuid [0-9a-f-]+\)", "(uuid %s)" % sheet, sch.read_text(), count=1)
    # Title block uses KiCad's ${PROJECTNAME} variable, so renaming stays consistent.
    sch.write_text(text.replace('\t(paper "A4")\n', '\t(paper "A4")\n' + TITLE_BLOCK, 1))
    return {"type": "native-defaults", "profile": profile_id,
            "source": "hardware/native-defaults (KiCad 10.0.7 blank schematic; board/project authored by "
                      "pcbnew from meta/templates/profiles/%s.json)" % profile_id}


def _migrate_models(board, variables):
    """KiCad 9 VRML references -> KiCad 10 STEP files that actually exist."""
    changes = []
    text = board.read_text(encoding="utf-8")

    def sub(m):
        rel = m.group(1)
        step = re.sub(r"\.wrl$", ".step", rel)
        target = Path(variables.get("KICAD10_3DMODEL_DIR", "")) / step
        if variables.get("KICAD10_3DMODEL_DIR") and target.is_file():
            changes.append({"from": m.group(0)[8:-1], "to": "${KICAD10_3DMODEL_DIR}/" + step})
            return '(model "${KICAD10_3DMODEL_DIR}/%s"' % step
        return m.group(0)

    text = re.sub(r'\(model "\$\{KICAD9_3DMODEL_DIR\}/([^"]+\.wrl)"', sub, text)
    board.write_text(text, encoding="utf-8")
    return changes


def _base_kicad_bundled(stage, name, base):
    support = kicad_env.shared_support()
    source = support / "template" / base["template"] if support else None
    if not source or not source.is_dir():
        raise KitError("KiCad's bundled template %s was not found; install KiCad %s."
                       % (base["template"], kicad_env.KICAD_VERSION), 10)
    old = base["project"]
    moves = base.get("library_moves", {})
    for path in sorted(source.iterdir()):
        if path.name in ("meta", "fp-info-cache") or path.suffix == ".kicad_prl":
            continue
        if path.name in moves:
            _copy(path, stage / moves[path.name])
        elif path.stem == old and path.suffix in (".kicad_pro", ".kicad_sch", ".kicad_pcb"):
            shutil.copy2(path, stage / (name + path.suffix))
        else:
            _copy(path, stage / path.name)
    pro, sch, pcb = (stage / (name + ext) for ext in (".kicad_pro", ".kicad_sch", ".kicad_pcb"))
    renamed = {
        "kicad_pro": _replace_exact(pro, '"filename": "%s.kicad_pro"' % old, '"filename": "%s.kicad_pro"' % _quote(name)),
        "kicad_sch": _replace_exact(sch, '(project "%s"' % old, '(project "%s"' % _quote(name), required=False),
        "kicad_pcb": _replace_exact(pcb, '(sheetfile "%s.kicad_sch")' % old, '(sheetfile "%s.kicad_sch")' % _quote(name),
                                    required=False),
    }
    table = stage / "fp-lib-table"
    for src_name, dst in moves.items():
        if table.is_file():
            _replace_exact(table, "${KIPRJMOD}/" + src_name, "${KIPRJMOD}/" + dst)
    migrations = _migrate_models(pcb, kicad_env.path_vars(stage)) if base.get("migrate_legacy_3d_models") else []
    return {"type": "kicad-bundled", "template": base["template"], "source": str(source),
            "attribution": base.get("attribution"), "renamed_references": renamed,
            "library_moves": moves, "model_migrations": migrations}


def resolve_profile(template, profile_id):
    profile_id = profile_id or template["default_profile"]
    if profile_id not in template["profiles"]:
        raise KitError("Template %s supports profile(s) %s, not %r." % (template["id"], ", ".join(template["profiles"]),
                                                                       profile_id))
    return profile_id


def materialize(template_id, stage, name, uuid_seed=None, profile_id=None, display=None):
    """Build a complete project tree for one template inside an empty stage dir."""
    validate_name(name)
    template = get_template(template_id)
    profile_id = resolve_profile(template, profile_id)
    stage = Path(stage)
    values = {"PROJECT_NAME": name, "TEMPLATE_TITLE": template["title"], "KIT_VERSION": KIT_VERSION,
              "KICAD_VERSION": kicad_env.KICAD_VERSION, "CREATED": now()[:10]}
    values.update(display or {})
    _apply_skeleton(stage, values)
    base = template["kicad_base"]
    if base["type"] == "native-defaults":
        provenance = _base_native_defaults(stage, name, uuid_seed, profile_id)
    elif base["type"] == "kicad-bundled":
        provenance = _base_kicad_bundled(stage, name, base)
    else:
        raise KitError("Unknown kicad_base type %r" % base["type"])
    for overlay in template.get("overlays", []):
        _copy(ROOT / overlay["from"], stage / overlay["to"])
    config_path = stage / "qa/verification.json"
    config = json.loads(config_path.read_text())
    config["gates"].update(template.get("verification", {}).get("gates", {}))
    write_json(config_path, config)
    record = {"schema": 1, "name": name, "template": template_id, "template_title": template["title"],
              "kit_version": KIT_VERSION, "kicad_version": kicad_env.KICAD_VERSION, "created": now(),
              "firmware": template["firmware"], "profile": profile_id, "kicad_base": provenance}
    write_json(stage / "meta/project.json", record)
    return record


def _outside_kit(path):
    path = Path(path).expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise KitError("Destination must be outside the kit repository: %s" % path)
    return path


def create(template_id, dest, name, git=False, register=True, profile_id=None):
    """Create an independent project; existing content is never merged or replaced."""
    validate_name(name)
    resolve_profile(get_template(template_id), profile_id)
    target = _outside_kit(dest)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise KitError("Destination exists and is not an empty directory; nothing was changed: %s" % target, 18)
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent, prefix=".project-stage-") as tmp:
        stage = Path(tmp) / "project"
        stage.mkdir()
        record = materialize(template_id, stage, name, profile_id=profile_id)
        if git:
            result = run(["git", "init", "--quiet", stage])  # repository only; never commits
            if result["exit_code"]:
                raise KitError("git init failed: " + result["stderr"])
        if target.exists():
            if any(target.iterdir()):
                raise KitError("Destination changed during creation; nothing was changed.", 18)
            target.rmdir()
        stage.rename(target)
    if register:
        from tools.project.registry import register_project

        register_project(target)
    return target, record


# -- native KiCad template installation ---------------------------------------
def _tree_hashes(folder):
    return {p.relative_to(folder).as_posix(): sha256(p) for p in sorted(folder.rglob("*"))
            if p.is_file() and p.relative_to(folder).as_posix() != MARKER}


def _build_native(template_id, stage):
    template = get_template(template_id)
    # KiCad renames files but not text, so README/AGENTS must not name the template id.
    materialize(template_id, stage, template_id, uuid_seed=template_id,
                display={"PROJECT_NAME": "New PCB project", "CREATED": "the day it was created in KiCad"})
    # KiCad omits meta/ when instantiating, so kit-only records stay out of new projects.
    shutil.copytree(Path(template["path"]) / "meta", stage / "meta", dirs_exist_ok=True)
    if template["kicad_base"]["type"] == "kicad-bundled":
        official_meta = kicad_env.shared_support() / "template" / template["kicad_base"]["template"] / "meta"
        for image in official_meta.glob("*.png"):
            shutil.copy2(image, stage / "meta" / image.name)
    # Timestamps in rendered READMEs and project.json are not part of identity.
    return {k: v for k, v in _tree_hashes(stage).items() if k not in ("README.md", "AGENTS.md", "meta/project.json")}


def native_status(dest=None):
    dest = Path(dest) if dest else kicad_env.user_template_dir()
    rows = []
    for template_id in templates():
        folder = dest / template_id
        marker = folder / MARKER
        if not folder.exists():
            state = "NOT_INSTALLED"
        elif not marker.is_file():
            state = "FOREIGN"  # exists but not installed by this kit
        else:
            data = json.loads(marker.read_text())
            current = _tree_hashes(folder)
            modified = [p for p, h in data["files"].items() if current.get(p) != h]
            if modified:
                state = "MODIFIED"
            else:
                # Compare content identity with what this kit would install now.
                with tempfile.TemporaryDirectory(prefix="kit-template-status-") as tmp:
                    stage = Path(tmp) / template_id
                    stage.mkdir()
                    try:
                        fresh = _build_native(template_id, stage)
                    except KitError:
                        fresh = None
                state = "INSTALLED" if fresh is None or data.get("identity") == fresh else "OUTDATED"
        rows.append({"template": template_id, "path": str(folder), "state": state})
    return {"template_dir": str(dest), "templates": rows}


def install_native(dest=None, update=False):
    """Install all templates into KiCad's user template dir; idempotent and non-destructive."""
    dest = Path(dest).expanduser() if dest else kicad_env.user_template_dir()
    _outside_kit(dest)
    dest.mkdir(parents=True, exist_ok=True)
    results = []
    for template_id in templates():
        folder = dest / template_id
        with tempfile.TemporaryDirectory(dir=dest, prefix=".kit-template-") as tmp:
            stage = Path(tmp) / template_id
            stage.mkdir()
            identity = _build_native(template_id, stage)
            marker = {"schema": 1, "kit_version": KIT_VERSION, "template": template_id, "identity": identity,
                      "installed": now(), "files": _tree_hashes(stage)}
            if folder.exists():
                existing = folder / MARKER
                if not existing.is_file():
                    results.append({"template": template_id, "action": "SKIPPED_FOREIGN", "path": str(folder),
                                    "reason": "directory exists and was not installed by this kit; left untouched"})
                    continue
                data = json.loads(existing.read_text())
                current = _tree_hashes(folder)
                if any(current.get(p) != h for p, h in data["files"].items()):
                    results.append({"template": template_id, "action": "SKIPPED_MODIFIED", "path": str(folder),
                                    "reason": "installed template was edited locally; left untouched"})
                    continue
                if data.get("identity") == identity:
                    results.append({"template": template_id, "action": "UNCHANGED", "path": str(folder)})
                    continue
                if not update:
                    results.append({"template": template_id, "action": "UPDATE_AVAILABLE", "path": str(folder),
                                    "reason": "re-run with --update to replace the unmodified older version"})
                    continue
                backup = folder.with_name(".%s.replaced-%s" % (template_id, now().replace(":", "")[:17]))
                folder.rename(backup)
                write_json(stage / MARKER, marker)
                stage.rename(folder)
                shutil.rmtree(backup)
                results.append({"template": template_id, "action": "UPDATED", "path": str(folder)})
                continue
            write_json(stage / MARKER, marker)
            stage.rename(folder)
            results.append({"template": template_id, "action": "INSTALLED", "path": str(folder)})
    return {"template_dir": str(dest), "results": results}
