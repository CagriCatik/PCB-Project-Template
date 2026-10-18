# Development kit architecture and commands

Shell entrypoints delegate to `tools/kit.py`; reusable logic lives in existing
`tools/`. There is no parallel application directory. The original installer,
`test_template.py`, `requirements.txt`, and `tools/verify.sh` remain entrypoints.

| Entry point | Behavior |
| --- | --- |
| `install_template.command`, `scripts/install-template.sh` | Interactive or `--parent PATH`; conservative native-template registration |
| `scripts/install-kicad.sh` | Official macOS 10.0.7 DMG installer; existing options preserved |
| `scripts/install-environment.sh` | Optional IPC client in global companion venv |
| `scripts/install-plugins.sh` | Default pinned InteractiveHtmlBom, FreeRouting archive support, `--diagnose` |
| `scripts/configure-kicad.sh PARENT` | Environment snippet and UI configuration instructions |
| `scripts/create-project.sh` | Prompted or `--name NAME --dest NEW_PATH`; `--firmware generic/stm32/arduino`, `--git`, `--no-register` |
| `scripts/open-project.sh PATH [--vscode]` | Open root project in KiCad or directory in VS Code |
| `scripts/verify.sh [PATH]`, `tools/verify.sh [PATH]` | Pinned ERC/DRC, parity, source hashes and run records |
| `scripts/export-manufacturing.sh PATH --revision REV` | Draft BOM/Gerber/drill/positions/STEP export plus manifest |
| `scripts/manage-libraries.sh symbol NAME FILE --project PATH` | Register an existing local `.kicad_sym` library |
| `scripts/manage-libraries.sh footprint NAME DIR --project PATH` | Register an existing local `.pretty` library |
| `scripts/firmware-build.sh stm32 PATH --preset NAME` | Configure/build a real vendor CMake preset |
| `scripts/firmware-build.sh arduino PATH --fqbn FQBN` | Build a real target sketch; no flashing |
| `scripts/diagnose.sh` | CLI version, IPC reachability, plugins and Java diagnostics |
| `python3 tools/kit.py ipc` | Read-only live API ping and version; exit 3 if unavailable |
| `python3 tools/kit.py git-status PATH` | Actual independent repository commit/dirty state |
| `scripts/package.sh --output ZIP` | Portable source archive outside the source tree |

Every entrypoint supports `--help`. `KICAD_KIT_PYTHON` selects the interpreter
used by shell wrappers; `KICAD_CLI` selects the actual KiCad executable.
The CLI always checks 10.0.7 before project generation, verification or export.

Project creation never merges an existing destination. It copies domain source,
adds exactly one matching native file triple using KiCad-generated defaults and
renews the blank schematic UUID. It can initialize Git but never stages,
commits, creates remotes or pushes. Registry entries are absolute machine-local
paths outside projects; use `--no-register` for isolated temporary creation.
The two native creation paths are independently checked: GUI creation by KiCad,
and CLI creation through exported KiCad-generated defaults.

Firmware selection records intent without creating a fake build. Follow
`firmware/tools/workflows.md` to import an actual MCU project or Arduino core.
Library registration requires assets already inside `hardware/libraries` and
uses `${KIPRJMOD}` paths. Existing names are preserved or refused on conflict.
No manufacturer assets are downloaded or fabricated.

The template source owns no root native design files; generated projects do.
A generated project may be used as source for another generic project: root
native files are excluded and new blank defaults are used. Template metadata
is needed for source-template operations; native GUI-created projects omit it
by KiCad design. Use the original template repository to install more templates.
