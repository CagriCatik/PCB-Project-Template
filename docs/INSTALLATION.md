# Installation

## Prerequisites

| Requirement | Notes |
| --- | --- |
| macOS (Apple silicon or Intel) | Tested on macOS 26.6.2 arm64 with zsh. |
| KiCad **10.0.7** in `/Applications/KiCad/` | Exact version enforced (exit 11 otherwise). Do not install KiCad 11 or nightlies. `scripts/install-kicad.sh --dmg FILE` installs an official DMG without replacing an existing installation (`--help`). |
| Python ≥ 3.10 | `python3` from Homebrew or python.org. The launcher picks the newest `python3.x` ≥ 3.10. |
| Git | Read-only use, plus `git init` on explicit `--git`. |
| Network (first run) | `pip` downloads `kicad-python` and its pinned dependencies. |
| Optional | VS Code, Java ≥ 25 (Freerouting 2.4.1), CMake + C compiler (firmware host tests), `arm-none-eabi-gcc` (STM32), PlatformIO (Arduino). |

## One-time installation

Double-click `install_template.command` in Finder, or run:

```sh
./install_template.command            # same as: scripts/kit install
```

The installer performs these steps and prints one status line per step:

1. **platform** – OS, version and architecture.
2. **kicad** – locates KiCad.app and `kicad-cli`, enforces 10.0.7, discovers CLI commands. Aborts before any write if this fails.
3. **tools** – Python, Git, VS Code, Java, firmware toolchains.
4. **python_venv** – creates `.venv` in the kit and installs `requirements.txt` (kicad-python 0.8.0 with its tested transitive pins, numpy 2.5.4 and scipy 1.18.1 for thermal analysis). A stamp file skips reinstalling unchanged requirements.
5. **kicad_templates** – installs `generic-pcb`, `stm32-embedded`, `arduino-shield` into KiCad's user template directory (`~/Documents/KiCad/10.0/template`, or `KICAD_USER_TEMPLATE_DIR`).
6. **plugins** – reads the PCM database and invokes each installed plugin headlessly; prints guided setup for missing ones.
7. **library_paths** – resolves every global symbol/footprint library (223/155 on a stock 10.0.7).
8. **ipc** – IPC configuration, process, socket and live-probe diagnostics.
9. **report** – `qa/generated/environment/install-report.json`.

Options: `--skip-venv`, `--template-dir DIR`, `--update-templates`,
`--no-plugin-verify`, `--report FILE`, `--json`.

## Idempotency and safety

- A second run reports `UNCHANGED` for the venv and templates and lists no
  changed steps; no installed file is rewritten.
- A template directory that exists without the kit's marker is reported
  `SKIPPED_FOREIGN` and left untouched. An installed template that was edited
  locally is `SKIPPED_MODIFIED`. A newer kit version shows `UPDATE_AVAILABLE`
  and replaces an unmodified template only with `--update-templates`.
- No system-wide configuration is changed and no `sudo` is used. KiCad's own
  settings are never edited by the installer; enabling the IPC API is a
  separate, explicit command (see `docs/KICAD_IPC.md`).
- Plugins are not installed unattended: KiCad's Plugin and Content Manager has
  no command-line interface. The report lists the exact guided steps.

## After installation

```sh
scripts/kit doctor                       # read-only re-check at any time
./project-manager.command                # interactive CLI manager
./gui.command                            # PySide6 desktop GUI (or: scripts/kit gui)
scripts/kit create --template generic-pcb --name "My Board" --dest "$HOME/Projects/My Board"
```

### Optional PySide6 Desktop GUI

The desktop application is an optional frontend for creating boards, running verification, and generating exports without replacing KiCad:

```sh
.venv/bin/pip install -r requirements-gui.txt
./gui.command                            # or: scripts/kit gui
```

Headless CLI automation and tests remain functional without PySide6.

KiCad reads user templates from that directory for **File > New Project from
Template**. The installed folders follow KiCad's template format (one
`.kicad_pro` plus `meta/info.html` with a title); the GUI dialog itself was not
exercised in this session (see `docs/ACCEPTANCE_REPORT.md`).

## Updating

1. Update the kit checkout (the repository owner pulls the new version).
2. Run `./install_template.command` again. Changed Python requirements are
   reinstalled into `.venv`; unchanged ones report `UNCHANGED`.
3. Templates whose content changed report `UPDATE_AVAILABLE`
   (`scripts/kit templates status` shows `OUTDATED`). Replace them with
   `./install_template.command --update-templates` (or
   `scripts/kit templates install --update`). Only unmodified kit-installed
   templates are replaced; locally edited ones are reported `SKIPPED_MODIFIED`
   and folders not installed by the kit `SKIPPED_FOREIGN`.
4. Existing projects are never changed by an update. New gates apply to them
   automatically with their default severities; adjust `qa/verification.json`
   in the project if needed.

## Verified installation scenarios (2026-10-18)

- Installation from a fresh copy of the repository (216 files) into isolated
  template and state directories, including creation of `.venv` from PyPI.
- Projects instantiated from the installed templates the way KiCad copies them
  load in `kicad-cli` with the source checkout renamed away, and pass the
  library, portability and pin/pad gates after being moved to another
  Unicode path.
- Repeated installation changes nothing; updates replace only unmodified
  kit templates. KiCad's own `default` template is never touched.

## Removing

Delete `.venv/`, the three folders under `~/Documents/KiCad/10.0/template/`
that contain `meta/kit-template.json`, and
`~/Library/Application Support/PCB-Project-Template/`. Generated projects are
independent and keep working with KiCad alone.
