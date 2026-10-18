"""Interactive project manager (launched by project-manager.command).

A thin text UI over the same functions the non-interactive CLI uses
(tools/cli/main.py); it holds no business logic of its own. Formal GO releases are
deliberately CLI-only (they need --approval and --authorize).
"""

from pathlib import Path
import sys

from tools import __version__
from tools.core import kicad_env
from tools.core.common import KitError, project_files

MENU = [
    ("1", "Create project"),
    ("2", "Open existing project"),
    ("3", "Open project in KiCad"),
    ("4", "Open project in VS Code"),
    ("5", "Run ERC/DRC and quality gates"),
    ("6", "Generate manufacturing outputs (draft)"),
    ("7", "Inspect plugin status"),
    ("8", "Diagnose environment"),
    ("9", "List registered projects"),
    ("0", "Exit"),
]


class Manager:
    def __init__(self, ask=input, say=print):
        self.ask, self.say = ask, say
        self.current = None

    # -- helpers --------------------------------------------------------------
    def prompt(self, text, default=None):
        suffix = " [%s]" % default if default else ""
        answer = self.ask("%s%s: " % (text, suffix)).strip()
        return answer or (default or "")

    def confirm(self, text):
        return self.prompt(text + " (y/N)").lower() in ("y", "yes")

    def need_project(self):
        if self.current:
            return self.current
        self.say("No project selected; choose one first.")
        self.open_existing()
        return self.current

    # -- actions --------------------------------------------------------------
    def create(self):
        from tools.project import templates as template_engine

        options = list(template_engine.templates().values())
        for i, t in enumerate(options, 1):
            self.say("  %d) %-16s %s" % (i, t["title"], t["description"][:90]))
        choice = self.prompt("Template number", "1")
        if not choice.isdigit() or not 1 <= int(choice) <= len(options):
            self.say("Invalid template choice.")
            return
        template = options[int(choice) - 1]
        profile = template["default_profile"]
        if len(template["profiles"]) > 1:
            for i, p in enumerate(template["profiles"], 1):
                self.say("  %d) %s" % (i, p))
            pick = self.prompt("Board profile (example stack-up/rules, see docs/engineering)", "1")
            if not pick.isdigit() or not 1 <= int(pick) <= len(template["profiles"]):
                self.say("Invalid profile choice.")
                return
            profile = template["profiles"][int(pick) - 1]
        for _attempt in range(3):
            name = self.prompt("Project name")
            try:
                template_engine.validate_name(name)
                break
            except KitError as exc:
                self.say("  " + str(exc))
        else:
            self.say("Giving up after three invalid names.")
            return
        parent = Path(self.prompt("Parent directory", str(kicad_env.documents_dir() / "projects"))).expanduser()
        dest = parent / name
        git = self.confirm("Initialize an empty Git repository (no commit)?")
        self.say("Template: %s (%s)\nProject:  %s\nLocation: %s" % (template["title"], profile, name, dest))
        if not self.confirm("Create it?"):
            self.say("Cancelled.")
            return
        path, _record = template_engine.create(template["id"], dest, name, git=git, profile_id=profile)
        self.current = path
        self.say("Created and selected: %s" % path)

    def open_existing(self):
        from tools.project import registry

        rows = [r for r in registry.list_projects() if r["exists"]]
        for i, r in enumerate(rows, 1):
            self.say("  %d) %s" % (i, r["path"]))
        answer = self.prompt("Number or project path")
        if answer.isdigit() and 1 <= int(answer) <= len(rows):
            path = Path(rows[int(answer) - 1]["path"])
        elif answer:
            path = Path(answer).expanduser().resolve()
        else:
            return
        project_files(path)  # raises a KitError for a non-project directory
        registry.register_project(path)
        self.current = path
        self.say("Selected: %s" % path)

    def open_kicad(self, vscode=False):
        from tools.project import registry

        path = self.need_project()
        if path:
            registry.open_project(path, vscode=vscode)
            self.say("Opened %s in %s." % (path.name, "VS Code" if vscode else "KiCad"))

    def verify(self):
        from tools.quality.verification import summary_lines, verify

        path = self.need_project()
        if path:
            self.say("Running KiCad %s checks..." % kicad_env.KICAD_VERSION)
            self.say("\n".join(summary_lines(verify(path))))

    def export(self):
        from tools.release.exports import export_project

        path = self.need_project()
        if not path:
            return
        revision = self.prompt("Revision label for this draft (e.g. A1)")
        target, manifest = export_project(path, revision)
        self.say("%s written to %s" % (manifest["label"], target))
        for name, state in manifest["outputs"].items():
            self.say("  %-22s %s" % (name, state))
        self.say("GO releases are CLI-only: scripts/kit export ... --approval FILE --authorize")

    def plugins(self):
        from tools.plugins import manager as plugins

        verify = self.confirm("Invoke plugins headlessly to verify them (takes ~30 s)?")
        result = plugins.diagnose(verify_plugins=verify)
        for p in result["plugins"]:
            self.say("  %-20s %-10s %s" % (p["name"], p["tier"], p["status"]))

    def doctor(self):
        from tools.environment.installer import doctor, report_lines

        self.say("\n".join(report_lines(doctor())))

    def list_projects(self):
        from tools.project import registry

        rows = registry.list_projects()
        if not rows:
            self.say("(no registered projects)")
        for r in rows:
            self.say("  %s %s %s" % ("✓" if r["exists"] else "✗ missing", r["path"], r.get("template") or ""))

    def run(self):
        actions = {"1": self.create, "2": self.open_existing, "3": self.open_kicad,
                   "4": lambda: self.open_kicad(vscode=True), "5": self.verify, "6": self.export,
                   "7": self.plugins, "8": self.doctor, "9": self.list_projects}
        while True:
            self.say("\nPCB Project Manager %s (KiCad %s)  current: %s" % (
                __version__, kicad_env.KICAD_VERSION, self.current or "none"))
            for key, label in MENU:
                self.say("  %s) %s" % (key, label))
            try:
                choice = self.prompt("Choose")
            except EOFError:
                return 0
            if choice in ("0", "10", "q", "exit"):
                return 0
            action = actions.get(choice)
            if not action:
                self.say("Unknown choice %r." % choice)
                continue
            try:
                action()
            except KitError as exc:
                self.say("ERROR: %s" % exc)
            except EOFError:
                return 0


def main():
    try:
        return Manager().run()
    except KeyboardInterrupt:
        print("\nBye.", file=sys.stderr)
        return 130
