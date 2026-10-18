"""kicad-cli adapter: version pinning, capability discovery, structured reports.

Commands and flags are discovered from the installed CLI's own ``--help`` output.
Calling a command or flag the installed version does not advertise raises
KitError instead of guessing.
"""

import json
import os
from pathlib import Path
import re

from tools.core import kicad_env
from tools.core.common import KitError, VERSION, run


class KiCadCLI:
    def __init__(self, executable=None, required_version=VERSION):
        path = Path(executable) if executable else kicad_env.kicad_cli_path()
        if not path or not path.is_file():
            raise KitError(
                "kicad-cli not found; install KiCad %s (expected %s) or set KICAD_CLI."
                % (VERSION, "/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli"),
                10,
            )
        self.executable = str(path)
        self.version_record = run([self.executable, "version"], timeout=60)
        self.version = self.version_record["stdout"].strip()
        self.version_status = "TESTED"
        if self.version_record["exit_code"] or not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise KitError("%s did not report a KiCad version (got %r)." % (self.executable, self.version), 11)
        if self.version != required_version:
            # Untested versions are refused unless explicitly allowed; then every report says so
            # and GO releases stay blocked.
            if os.environ.get("KICAD_KIT_ALLOW_UNTESTED") != "1":
                raise KitError(
                    "KiCad %s required; %s reports %r. Set KICAD_KIT_ALLOW_UNTESTED=1 to run checks "
                    "anyway (results are marked UNTESTED; releases stay blocked)."
                    % (required_version, self.executable, self.version), 11)
            self.version_status = "UNTESTED"
        self._help = {}

    # -- capability discovery -------------------------------------------------
    def help(self, *path):
        """Parsed help for one command path, or None if the CLI does not have it."""
        if path in self._help:
            return self._help[path]
        record = run([self.executable, *path, "--help"], timeout=60)
        usage = next((l for l in record["stdout"].splitlines() if l.startswith("Usage:")), "")
        words = usage[len("Usage:"):].split()
        if words[:1] == ["kicad-cli"]:
            words = words[1:]
        parsed = None
        # Usage names the last two path components ("export step"); an unknown
        # subcommand prints its parent's help instead, so require a match.
        tail = list(path[-2:])
        if usage and words[: len(tail)] == tail:
            braces = re.search(r"\{([^}]*)\}", usage)
            parsed = {
                "subcommands": braces.group(1).split(",") if braces else [],
                "options": sorted(set(re.findall(r"(--[A-Za-z0-9][A-Za-z0-9-]*)", record["stdout"]))),
            }
        self._help[path] = parsed
        return parsed

    def supports(self, *path, option=None):
        info = self.help(*path)
        return bool(info) and (option is None or option in info["options"])

    def capabilities(self):
        """Full discovered command tree: {"pcb export step": [options...], ...}."""
        tree = {}

        def walk(path):
            info = self.help(*path)
            if not info:
                return
            if info["subcommands"]:
                for sub in info["subcommands"]:
                    walk(path + (sub,))
            elif path:
                tree[" ".join(path)] = info["options"]

        walk(())
        return tree

    def require(self, path, options=()):
        if not self.supports(*path):
            raise KitError("kicad-cli %s does not provide '%s'." % (self.version, " ".join(path)), 15)
        missing = [o for o in options if not self.supports(*path, option=o)]
        if missing:
            raise KitError(
                "kicad-cli %s '%s' lacks option(s): %s" % (self.version, " ".join(path), ", ".join(missing)),
                15,
            )

    # -- invocation -----------------------------------------------------------
    def call(self, *args, timeout=300, cwd=None):
        return run([self.executable, *args], timeout=timeout, cwd=cwd)

    def command(self, path, args, timeout=300):
        """Run a discovered command; every --flag in args must be advertised."""
        self.require(path, [a for a in map(str, args) if a.startswith("--")])
        return self.call(*path, *args, timeout=timeout)

    def erc(self, schematic, output):
        record = self.command(
            ("sch", "erc"),
            ["--format", "json", "--severity-all", "--exit-code-violations", "--output", output, schematic],
        )
        return record, _load_report(output)

    def drc(self, board, output, parity=True):
        args = ["--format", "json", "--severity-all", "--exit-code-violations", "--output", output]
        if parity:
            args.append("--schematic-parity")
        record = self.command(("pcb", "drc"), args + [board])
        return record, _load_report(output)


def _load_report(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def summarize_erc(report):
    """Split ERC violations into active findings and reviewed exclusions."""
    if not isinstance(report, dict) or not isinstance(report.get("sheets"), list):
        return {"valid": False, "active": [], "excluded": []}
    active, excluded = [], []
    for sheet in report["sheets"]:
        if not isinstance(sheet.get("violations"), list):
            return {"valid": False, "active": [], "excluded": []}
        for v in sheet["violations"]:
            item = {"sheet": sheet.get("path", "/"), **v}
            (excluded if _is_excluded(v) else active).append(item)
    return {"valid": True, "active": active, "excluded": excluded}


def summarize_drc(report):
    keys = ("violations", "unconnected_items", "schematic_parity")
    if not isinstance(report, dict) or not all(isinstance(report.get(k), list) for k in keys):
        return {"valid": False, **{k: [] for k in keys}, "excluded": []}
    result = {"valid": True, "excluded": []}
    for key in keys:
        result[key] = []
        for v in report[key]:
            (result["excluded"] if _is_excluded(v) else result[key]).append({"kind": key, **v})
    return result


def _is_excluded(v):
    return v.get("excluded") is True or v.get("severity") == "exclusion"
