# CLI reference

`scripts/kit` runs `python -m tools` (`tools/cli/main.py`) with the kit's `.venv` (or the newest
`python3.x` ≥ 3.10). Output is human-readable; add `--json` to any command for
the complete machine-readable result. Relative paths resolve against your
current directory. Every command supports `--help`.

## Environment

| Command | Purpose |
| --- | --- |
| `scripts/kit install [--skip-venv] [--template-dir DIR] [--update-templates] [--no-plugin-verify] [--report FILE]` | One-time, idempotent installation (also `./install_template.command`). |
| `scripts/kit doctor [--verify-plugins] [--report FILE]` | Read-only diagnostics of the same areas. |
| `scripts/kit version` | Kit version, required and installed KiCad. |
| `scripts/kit cli capabilities` | Commands discovered from the installed `kicad-cli`. |
| `scripts/kit libraries check [PROJECT]` | Resolve all global (and project) library tables. |
| `scripts/kit libraries register PROJECT --kind symbol\|footprint --name NAME --source PATH` | Add a `${KIPRJMOD}` entry for a library already under `hardware/libraries`; never replaces an entry. |

## Templates and projects

| Command | Purpose |
| --- | --- |
| `scripts/kit templates list` | The three templates and the board profiles each supports. |
| `scripts/kit templates profiles` | Board profiles (`2-layer`, `4-layer`): example stack-up, rule minimums, net classes. |
| `scripts/kit templates rebuild-profiles` | Maintainers: re-author the profile defaults with pcbnew (needs KiCad 10.0.7). |
| `scripts/kit templates status [--dest DIR]` | `NOT_INSTALLED` / `INSTALLED` / `OUTDATED` / `MODIFIED` / `FOREIGN` per template. |
| `scripts/kit templates install [--dest DIR] [--update]` | Install into KiCad's user template directory. |
| `scripts/kit create --template ID --name NAME --dest DIR [--profile 2-layer\|4-layer] [--git] [--no-register]` | Create an independent project; `--git` only runs `git init`. Arduino Shield uses KiCad's official board (`official`). |
| `scripts/kit projects list\|add PATH\|forget PATH` | Machine-local project registry. |
| `scripts/kit open PROJECT [--vscode]` | Open in KiCad (default) or VS Code. |
| `scripts/kit manager` | Interactive menu (also `./project-manager.command`). |

## Verification and manufacturing

| Command | Purpose |
| --- | --- |
| `scripts/kit verify PROJECT [--gate NAME ...] [--release]` | Quality gates; `--release` applies release severities. |
| `scripts/kit export PROJECT --revision REV [--no-ibom]` | NO-GO draft to `manufacturing/releases/generated/rev-REV-DRAFT`. |
| `scripts/kit export PROJECT --revision REV --approval FILE --authorize` | GO release (all release conditions must hold). |
| `scripts/kit releases PROJECT` | Status of every existing export: CURRENT, STALE (sources changed), MODIFIED (files changed), INCOMPLETE. Exit 21 unless all CURRENT. |
| `scripts/kit compare-exports MANIFEST_A MANIFEST_B` | Reproducibility check of two exports. |
| `scripts/kit components list\|validate PROJECT` | Component records. |
| `scripts/kit components add PROJECT --manufacturer M --mpn P [--symbol S --footprint F --datasheet-url U --revision R]` | New `candidate` record; never overwrites. |
| `scripts/kit firmware PROJECT --target host\|stm32\|arduino` | Firmware build/tests. |
| `scripts/kit thermal analyze PROJECT [--power REF=W ...] [--ambient C] [--grid MM] [--output DIR]` | Steady-state thermal estimate; see `docs/THERMAL_ANALYSIS.md`. |
| `scripts/kit thermal compare RUN_A RUN_B` | Temperature deltas between two thermal runs. |

## Plugins and IPC

| Command | Purpose |
| --- | --- |
| `scripts/kit plugins status\|verify [NAME]\|updates\|guide NAME` | See `docs/PLUGIN_MANAGEMENT.md`. |
| `scripts/kit plugins install-ibom [--dest DIR --source DIR]` | Optional pinned manual IBOM install. |
| `scripts/kit plugins install-archive NAME --archive ZIP --sha256 HASH [--user-root DIR]` | Optional reviewed PCM-ZIP payload install. |
| `scripts/kit ipc status [--timeout-ms N]` | IPC diagnostics and live probe. |
| `scripts/kit ipc enable [--apply]` | Enable the API server while KiCad is closed. |
| `scripts/kit package --output FILE` | Source ZIP of the kit, outside the repository. |

Shell aliases in `scripts/` map to these commands: `install-template.sh`,
`install-environment.sh` → `install`; `configure-kicad.sh` → `templates install`;
`create-project.sh` → `create`; `diagnose.sh` → `doctor`; `verify.sh` and
`tools/verify.sh` → `verify`; `export-manufacturing.sh` → `export`;
`firmware-build.sh` → `firmware`; `manage-libraries.sh` → `libraries`;
`open-project.sh` → `open`; `install-plugins.sh` → `plugins` (default `status`);
`thermal-analysis.sh` → `thermal`;
`package.sh` → `package`. `install-kicad.sh` installs the official KiCad DMG;
`install-vscode-extensions.sh [--optional] [--no-firmware] [--update] [--dry-run]`
installs the recommended VS Code extensions (`--list` shows them).

## Exit codes

| Code | Meaning |
| --- | --- |
| 0 | Success / gate PASS |
| 1 | Installer or doctor reported FAIL |
| 2 | Usage or validation error (for example invalid project name) |
| 3 | IPC unavailable, or plugin update check offline |
| 4 | A required plugin is not ready / not verified |
| 10 | `kicad-cli` not found |
| 11 | Installed KiCad is not 10.0.7 (and `KICAD_KIT_ALLOW_UNTESTED=1` not set), or no version reported |
| 12 / 13 | No single root `.kicad_pro` / matching `.kicad_sch` and `.kicad_pcb` missing or unreadable |
| 14 | Editor lock files present (design open in KiCad) |
| 15 | Command or flag not provided by the installed `kicad-cli` |
| 16 | KiCad is running (refused config change) |
| 17 | Firmware target not configured or toolchain missing |
| 18 | Project destination exists and is not empty |
| 19 | Thermal inputs missing (no power sources) or numpy/scipy not installed |
| 20 | Verification or thermal FAIL |
| 21 | Export incomplete, revision already exported, or exports differ |
| 22 | Release blocked |

## Environment variables

`KICAD_APP`, `KICAD_CLI`, `KICAD_PCBNEW_PYTHON`, `KICAD_CONFIG_HOME`,
`KICAD_DOCUMENTS_HOME`, `KICAD_USER_TEMPLATE_DIR`, `KICAD_KIT_HOME`,
`KICAD_KIT_PYTHON` (interpreter for `scripts/kit`), `KICAD_KIT_IPC_PYTHON`,
`KICAD_API_SOCKET`, `KICAD_NATIVE_TESTS=0` (skip native tests),
`ARM_GNU_TOOLCHAIN_BIN` (Arm GNU Toolchain `bin/` for `--target stm32`),
`STM32CUBE_REPOSITORY` (STM32Cube package repository for `doctor`),
`KIT_STM32_CUBEMX_SOURCE` / `KIT_STM32_STATUS_LED` (opt-in real STM32 cross-build test),
`KICAD_KIT_ALLOW_UNTESTED=1` (run with another KiCad version; results marked
UNTESTED, GO releases blocked — see `docs/KICAD_COMPATIBILITY.md`).
