"""Non-interactive CLI for PCB-Project-Template (the shared automation core).

Run with ``scripts/kit`` (or ``python -m tools`` from the kit root).

Human-readable output by default, full JSON with --json. Exit codes:
0 ok | 2 usage/validation | 3 IPC unavailable | 4 plugin not verified
10 kicad-cli missing | 11 wrong KiCad version | 12/13 project files | 14 lock files
15 CLI capability missing | 16 KiCad running | 17 firmware toolchain/config
18 destination exists | 19 thermal inputs/dependencies missing | 20 verification or thermal FAIL
21 export incomplete | 22 release blocked
"""

import argparse
import json
from pathlib import Path
import sys

from tools import __version__
from tools.core.common import KitError

LEGACY_FIRMWARE = {"generic": "generic-pcb", "stm32": "stm32-embedded", "arduino": "arduino-shield"}


def _emit(args, data, lines=None):
    if getattr(args, "json", False) or lines is None:
        print(json.dumps(data, indent=2, default=str))
    else:
        print("\n".join(lines))


def build_parser():
    p = argparse.ArgumentParser(prog="kit", description="PCB-Project-Template %s (KiCad 10.0.7)" % __version__)
    sub = p.add_subparsers(dest="command", required=True)

    def cmd(name, help_text):
        c = sub.add_parser(name, help=help_text)
        c.add_argument("--json", action="store_true", help="print full JSON")
        return c

    c = cmd("install", "one-time, idempotent environment installation")
    c.add_argument("--skip-venv", action="store_true")
    c.add_argument("--template-dir")
    c.add_argument("--update-templates", action="store_true")
    c.add_argument("--no-plugin-verify", action="store_true")
    c.add_argument("--report")
    c = cmd("doctor", "read-only environment diagnostics")
    c.add_argument("--verify-plugins", action="store_true")
    c.add_argument("--report")

    c = cmd("templates", "list or install native KiCad templates")
    c.add_argument("action", choices=["list", "profiles", "status", "install", "rebuild-profiles"])
    c.add_argument("--dest")
    c.add_argument("--update", action="store_true")

    c = cmd("create", "create an independent project from a template")
    c.add_argument("--template", choices=["generic-pcb", "stm32-embedded", "arduino-shield"])
    c.add_argument("--firmware", choices=sorted(LEGACY_FIRMWARE), help=argparse.SUPPRESS)
    c.add_argument("--name", required=True)
    c.add_argument("--dest", required=True, help="new (or empty) project directory")
    c.add_argument("--profile", help="board profile (templates list shows the supported ones)")
    c.add_argument("--git", action="store_true", help="git init only; never commits")
    c.add_argument("--no-register", action="store_true")

    c = cmd("projects", "registered projects")
    c.add_argument("action", choices=["list", "add", "forget"])
    c.add_argument("path", nargs="?")

    c = cmd("open", "open a project in KiCad or VS Code")
    c.add_argument("project")
    c.add_argument("--vscode", action="store_true")

    c = cmd("verify", "run quality gates (ERC, DRC, parity, libraries, metadata, 3D, BOM, firmware)")
    c.add_argument("project")
    c.add_argument("--gate", action="append", dest="gates")
    c.add_argument("--release", action="store_true", help="apply release gate severities")

    c = cmd("export", "manufacturing outputs: NO-GO draft, or GO release with --approval --authorize")
    c.add_argument("project")
    c.add_argument("--revision", required=True)
    c.add_argument("--approval")
    c.add_argument("--authorize", action="store_true", help="explicit user authorization for a GO release")
    c.add_argument("--no-ibom", action="store_true")
    c = cmd("releases", "status of existing exports: CURRENT, STALE, MODIFIED or INCOMPLETE")
    c.add_argument("project")
    c = cmd("compare-exports", "check two export manifests for reproducibility")
    c.add_argument("manifest_a")
    c.add_argument("manifest_b")

    c = cmd("plugins", "plugin status, verification, updates and guided setup")
    c.add_argument("action", choices=["status", "verify", "updates", "guide", "install-ibom", "install-archive"])
    c.add_argument("name", nargs="?")
    c.add_argument("--archive")
    c.add_argument("--sha256")
    c.add_argument("--dest")
    c.add_argument("--source")
    c.add_argument("--user-root")

    c = cmd("ipc", "KiCad IPC API diagnostics and configuration")
    c.add_argument("action", choices=["status", "enable"])
    c.add_argument("--apply", action="store_true", help="with enable: write the change (KiCad must be closed)")
    c.add_argument("--timeout-ms", type=int, default=3000)

    c = cmd("cli", "kicad-cli adapter information")
    c.add_argument("action", choices=["capabilities"])

    c = cmd("components", "component records")
    c.add_argument("action", choices=["list", "validate", "add"])
    c.add_argument("project")
    c.add_argument("--manufacturer")
    c.add_argument("--mpn")
    c.add_argument("--symbol", default="")
    c.add_argument("--footprint", default="")
    c.add_argument("--datasheet-url", default="")
    c.add_argument("--revision", default="")

    c = cmd("libraries", "library table checks and project-local registration")
    c.add_argument("action", choices=["check", "register"])
    c.add_argument("project", nargs="?")
    c.add_argument("--kind", choices=["symbol", "footprint"])
    c.add_argument("--name")
    c.add_argument("--source")

    c = cmd("thermal", "steady-state thermal estimate (heatmaps, hotspots, component temperatures)")
    c.add_argument("action", choices=["analyze", "compare"])
    c.add_argument("project", help="project directory (analyze) or first thermal.json (compare)")
    c.add_argument("other", nargs="?", help="second thermal.json (compare)")
    c.add_argument("--power", action="append", metavar="REF=W", help="add/override a power source (estimate)")
    c.add_argument("--ambient", type=float)
    c.add_argument("--grid", type=float, help="cell size in mm")
    c.add_argument("--output", help="output directory (default: <project>/qa/generated/thermal/<run>)")

    c = cmd("firmware", "optional firmware build/test")
    c.add_argument("project")
    c.add_argument("--target", choices=["host", "stm32", "arduino"], default="host")

    cmd("manager", "interactive project manager")
    cmd("version", "kit and KiCad versions")
    c = cmd("package", "source ZIP of the kit (outside the repository)")
    c.add_argument("--output", required=True)
    return p


def run_command(args):
    c = args.command
    if c == "install":
        from tools.environment import installer as env

        report = env.install(args.skip_venv, args.template_dir, args.update_templates,
                             not args.no_plugin_verify, args.report)
        _emit(args, report, env.report_lines(report))
        return 1 if report["overall"] == "FAIL" else 0
    if c == "doctor":
        from tools.environment import installer as env

        report = env.doctor(args.report, args.verify_plugins)
        _emit(args, report, env.report_lines(report))
        return 1 if report["overall"] == "FAIL" else 0
    if c == "templates":
        from tools.project import templates as t

        if args.action == "list":
            rows = [{"id": k, "title": v["title"], "profiles": v["profiles"], "description": v["description"]}
                    for k, v in t.templates().items()]
            _emit(args, rows, ["%-16s %-16s profiles: %s" % (r["id"], r["title"], ", ".join(r["profiles"]))
                               for r in rows])
        elif args.action == "profiles":
            from tools.project import profiles

            rows = [{"id": k, "title": v["title"], "copper_layers": v["copper_layers"],
                     "thickness_mm": profiles.board_thickness(v), "rules": v["rules"], "netclasses": v["netclasses"]}
                    for k, v in profiles.profiles().items()]
            _emit(args, rows, ["%-8s %s" % (r["id"], r["title"]) for r in rows] +
                  ["Values are examples; confirm them with your fabricator (see docs/engineering/)."])
        elif args.action == "rebuild-profiles":
            from tools.project import profiles

            rows = {k: profiles.build(k, profiles.DEFAULTS_DIR / k) for k in profiles.profiles()}
            _emit(args, rows, ["%-8s pcbnew read-back: %s" % (k, v) for k, v in rows.items()])
        elif args.action == "status":
            s = t.native_status(args.dest)
            _emit(args, s, [s["template_dir"]] + ["  %-16s %s" % (r["template"], r["state"]) for r in s["templates"]])
        else:
            s = t.install_native(args.dest, args.update)
            _emit(args, s, [s["template_dir"]] + ["  %-16s %s" % (r["template"], r["action"]) for r in s["results"]])
        return 0
    if c == "create":
        from tools.project import templates as t

        template = args.template or LEGACY_FIRMWARE.get(args.firmware or "", None)
        if not template:
            raise KitError("Choose --template generic-pcb | stm32-embedded | arduino-shield.")
        path, record = t.create(template, args.dest, args.name, args.git, not args.no_register, args.profile)
        _emit(args, {"project": str(path), "record": record},
              ["Created %s project (%s profile): %s" % (record["template_title"], record["profile"], path),
               "Next: scripts/kit open \"%s\"   |   scripts/kit verify \"%s\"" % (path, path)])
        return 0
    if c == "projects":
        from tools.project import registry

        if args.action == "list":
            rows = registry.list_projects()
            _emit(args, rows, ["%s %-60s %s" % ("✓" if r["exists"] else "✗", r["path"], r.get("template") or "")
                               for r in rows] or ["(no registered projects)"])
        else:
            if not args.path:
                raise KitError("projects %s needs a path" % args.action)
            if args.action == "add":
                from tools.core.common import project_files

                project_files(Path(args.path).expanduser().resolve())
                data = registry.register_project(Path(args.path).expanduser())
            else:
                data = registry.forget_project(args.path)
            _emit(args, data, ["%d registered project(s)" % len(data["projects"])])
        return 0
    if c == "open":
        from tools.project import registry

        record = registry.open_project(args.project, args.vscode)
        _emit(args, record, ["Opened: " + " ".join(record["argv"])])
        return 0
    if c == "verify":
        from tools.quality.verification import summary_lines, verify

        result = verify(args.project, gates=args.gates, release=args.release)
        _emit(args, result, summary_lines(result))
        return 0 if result["quality_gate"] == "PASS" else 20
    if c == "export":
        from tools.release.exports import export_project

        target, manifest = export_project(args.project, args.revision, args.approval, authorize=args.authorize,
                                          ibom=not args.no_ibom)
        lines = ["%s -> %s" % (manifest["label"], target), "Quality gate: %s %s" % (
            manifest["quality_gate"], ("(blocking: %s)" % ", ".join(manifest["blocking_gates"]))
            if manifest["blocking_gates"] else "")]
        lines += ["  %-22s %s" % (k, v) for k, v in manifest["outputs"].items()]
        lines += ["  ! %s %s" % (f["problem"], f.get("reference", "")) for f in manifest["designator_findings"]]
        _emit(args, {"directory": str(target), "manifest": manifest}, lines)
        return 0 if manifest["exports_complete"] else 21
    if c == "releases":
        from tools.release.exports import release_status

        rows = release_status(args.project)
        _emit(args, rows, ["%-24s %-10s %s" % (r["release"], r["status"], r.get("detail") or "") for r in rows]
              or ["(no exports)"])
        return 0 if all(r["status"] == "CURRENT" for r in rows) else 21
    if c == "compare-exports":
        from tools.release.exports import compare_manifests

        result = compare_manifests(args.manifest_a, args.manifest_b)
        _emit(args, result, ["Reproducible: %s (%d artifacts compared)" % (result["identical"], result["compared"])]
              + ["  differs: " + d for d in result["differences"]])
        return 0 if result["identical"] else 21
    if c == "plugins":
        return _plugins(args)
    if c == "ipc":
        from tools.kicad import ipc

        if args.action == "enable":
            result = ipc.enable_server(apply=args.apply)
            _emit(args, result, ["%s: %s" % (result["status"], result["config_file"])] +
                  ([result["next"]] if "next" in result else []))
            return 0
        result = ipc.save_report(ipc.diagnose(args.timeout_ms))
        conn = result["connection"] or {}
        lines = ["IPC: %s" % result["status"],
                 "  api.enable_server: %s (%s)" % (result["config"]["enable_server"], result["config"]["config_file"]),
                 "  KiCad processes:   %s" % (", ".join(str(p["pid"]) for p in result["kicad_processes"]) or "none"),
                 "  sockets:           %s" % (", ".join(s["uri"] for s in result["sockets"]) or "none found"),
                 "  client:            %s" % (result["client_python"] or "kicad-python not installed")]
        if conn:
            lines.append("  server version:    %s" % conn.get("versions", {}).get("server"))
            lines.append("  board:             %s" % json.dumps(conn.get("board")))
        lines += ["  ! " + x for x in result["causes"]]
        _emit(args, result, lines)
        return 0 if result["reachable"] else 3
    if c == "cli":
        from tools.kicad.cli import KiCadCLI

        cli = KiCadCLI()
        caps = cli.capabilities()
        _emit(args, {"version": cli.version, "executable": cli.executable, "commands": caps},
              ["kicad-cli %s (%s): %d commands" % (cli.version, cli.executable, len(caps))] +
              ["  " + k for k in sorted(caps)])
        return 0
    if c == "components":
        from tools.project import components

        if args.action == "add":
            path = components.add(args.project, args.manufacturer or "", args.mpn or "", args.symbol, args.footprint,
                                  args.datasheet_url, args.revision)
            _emit(args, {"record": str(path)}, ["Created candidate record: %s" % path])
            return 0
        if args.action == "list":
            records, problems = components.load_records(args.project)
            rows = [{"file": str(p), "manufacturer": d.get("manufacturer"), "mpn": d.get("mpn"),
                     "status": (d.get("approval") or {}).get("status")} for p, d in records]
            _emit(args, {"records": rows, "problems": problems},
                  ["%-20s %-28s %s" % (r["manufacturer"], r["mpn"], r["status"]) for r in rows] or ["(no records)"])
            return 0
        result = components.validate(args.project)
        _emit(args, result, ["Components: %s (%d records, %d approved)" % (result["status"], result["records"],
                                                                         result["approved"])] +
              ["  %s: %s" % (Path(f["file"]).name, f["problem"]) for f in result["findings"]])
        return 0 if result["status"] == "PASS" else 20
    if c == "libraries":
        from tools.kicad.libraries import LibraryTables, register_library

        if args.action == "register":
            if not (args.project and args.kind and args.name and args.source):
                raise KitError("libraries register needs PROJECT --kind --name --source")
            table = register_library(args.project, args.kind, args.name, args.source)
            _emit(args, {"table": str(table)}, ["Registered in " + str(table)])
            return 0
        summary = LibraryTables(args.project).summary()
        broken = summary["symbol"]["broken"] + summary["footprint"]["broken"]
        _emit(args, summary, ["symbol libraries: %d, footprint libraries: %d, broken: %d" % (
            summary["symbol"]["libraries"], summary["footprint"]["libraries"], len(broken))] +
              ["  broken: %s (%s)" % (b["name"], b["uri"]) for b in broken] + ["  ! " + x for x in summary["problems"]])
        return 0 if not broken and not summary["problems"] else 20
    if c == "thermal":
        if args.action == "compare":
            from tools.thermal.compare import compare, compare_lines

            if not args.other:
                raise KitError("thermal compare needs two thermal.json files")
            result = compare(args.project, args.other)
            _emit(args, result, compare_lines(result))
            return 0
        from tools.thermal.analysis import analyze, summary_lines

        result = analyze(args.project, args.output, args.ambient, args.grid, args.power)
        _emit(args, result, summary_lines(result))
        return 0 if result["status"] == "PASS" else 20
    if c == "firmware":
        from tools.quality.firmware import build

        result = build(args.project, args.target)
        _emit(args, result, ["Firmware %s: %s" % (args.target, result["status"])] +
              ["  $ %s -> %d" % (" ".join(r["argv"]), r["exit_code"]) for r in result["commands"]])
        return 0 if result["status"] == "PASS" else 20
    if c == "manager":
        from tools.cli.interactive import main as manager_main

        return manager_main()
    if c == "version":
        from tools.core import kicad_env

        info = {"kit": __version__, "kicad_required": kicad_env.KICAD_VERSION}
        try:
            from tools.kicad.cli import KiCadCLI

            info["kicad_installed"] = KiCadCLI().version
        except KitError as exc:
            info["kicad_installed"] = str(exc)
        _emit(args, info, ["PCB-Project-Template %(kit)s; KiCad required %(kicad_required)s; installed: "
                           "%(kicad_installed)s" % info])
        return 0
    if c == "package":
        from tools.release.packaging import package

        result = package(Path(__file__).resolve().parents[2], args.output)
        _emit(args, result, ["Archive: %(archive)s (%(files)d files)" % result])
        return 0
    raise KitError("Unknown command %s" % c)


def _plugins(args):
    from tools.plugins import manager as plugins

    if args.action == "status":
        result = plugins.diagnose(verify_plugins=False)
    elif args.action == "verify":
        if args.name:
            if args.name not in plugins.PLUGINS:
                raise KitError("Unknown plugin %r; choose: %s" % (args.name, ", ".join(plugins.PLUGINS)))
            row = plugins.verify(args.name)
            _emit(args, row, ["%s: %s  %s" % (row["name"], row["status"], row["verification"].get("evidence")
                                              or row["verification"].get("reason") or "")])
            return 0 if row["status"] == "VERIFIED" else 4
        result = plugins.diagnose(verify_plugins=True)
    elif args.action == "updates":
        result = plugins.check_updates()
        _emit(args, result, ["PCM repository: %s (updated %s)" % (result["status"], result.get("repository_updated"))]
              + ["  %-20s installed=%-8s latest=%-8s %s" % (r["name"], r.get("installed"), r.get("latest_compatible"),
                                                            r["status"]) for r in result.get("plugins", [])]
              + ([result["error"]] if result.get("error") else []))
        return 0 if result["status"] == "OK" else 3
    elif args.action == "guide":
        if args.name not in plugins.PLUGINS:
            raise KitError("plugins guide needs one of: %s" % ", ".join(plugins.PLUGINS))
        g = plugins.guide(args.name)
        _emit(args, g, ["%s (%s)" % (g["name"], g["homepage"])] + ["  %d. %s" % (i + 1, s) for i, s in
                                                                  enumerate(g["steps"])])
        return 0
    elif args.action == "install-ibom":
        result = plugins.install_ibom(args.dest, args.source)
        _emit(args, result, ["InteractiveHtmlBom: %s (%s)" % (result["status"], result.get("path"))])
        return 0
    else:
        if not (args.name and args.archive and args.sha256):
            raise KitError("install-archive needs NAME --archive FILE --sha256 HASH")
        result = plugins.install_archive(args.name, args.archive, args.sha256, args.user_root)
        _emit(args, result, ["%s: %s (%s)" % (args.name, result["status"], result.get("path"))])
        return 0
    lines = ["PCM database: %s" % result["pcm_database"], "Java major: %s" % result["java_major"]]
    lines += ["  %-20s %-10s %-28s pcm=%-8s py=%s" % (p["name"], p["tier"], p["status"], p.get("pcm_version"),
                                                    p.get("python_package_version")) for p in result["plugins"]]
    lines += ["  note: " + n for n in result["notes"]]
    _emit(args, result, lines)
    return 0 if result["required_ready"] else 4


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        return run_command(args)
    except KitError as exc:
        print("ERROR: %s" % exc, file=sys.stderr)
        return exc.exit_code
    except (OSError, ValueError) as exc:
        print("ERROR: %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
