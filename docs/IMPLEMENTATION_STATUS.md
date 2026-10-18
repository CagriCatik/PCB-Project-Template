# Implementation status

Kit version 2.0.0, implemented 2026-10-18 in the existing local checkout. No
Git staging, commits or pushes were made; all changes are uncommitted.

## Baseline (phase 1 audit, before any change)

| Item | Observed |
| --- | --- |
| Repository | local checkout under the developer's home directory, branch `main`, remote `https://github.com/CagriCatik/PCB-Project-Template.git`, one commit `61ac6b4 Initial commit` (tracks only `LICENSE`, `README.md`). |
| Working tree | `LICENSE` and `README.md` modified; everything else untracked local work from an earlier single-template iteration (`tools/` ≈1,500 lines, 13 scripts, 24 passing tests, docs, 7 old QA run folders). `README Kopie.md` had already been removed by that iteration with the owner's authorization. |
| Earlier architecture | The repo root itself was one KiCad template ("Embedded HW + FW") copied wholesale (including `tools/` and `scripts/`) into each project; one firmware flag; ERC/DRC and five export types; IBOM/FreeRouting diagnostics; IPC ping. |
| OS / shell | macOS 26.6.2 (25G83), arm64, zsh. |
| KiCad | 10.0.7 release build at `/Applications/KiCad/KiCad.app`; `kicad-cli` 10.0.7; `KICAD_IPC_API=ON`; bundled Python 3.9.13 with pcbnew 10.0.7. **KiCad GUI running (PID 7129).** |
| Python | Homebrew 3.13.5 (no `kipy`); `kicad-python` 0.8.0 only in `~/Library/Application Support/PCB-Project-Template/venv` (from the earlier iteration). |
| Other tools | Git 2.50.1, VS Code 1.141.2 (`code`), Java Temurin 27, CMake, Apple clang 17. Not installed: `arm-none-eabi-gcc`, `arduino-cli`, PlatformIO, `kibot`, `kikit` on PATH. |
| PCM plugins | `installed_packages.json` (config dir): Freerouting 2.4.1, InteractiveHtmlBom 2.12.0, KiKit 1.6.0 (shim; `kikit` 1.8.1 present in KiCad's Python), kicadroutingtools 0.0. Stale second database in `~/Documents/KiCad/10.0/3rdparty/`. Not installed: KiBuzzard, Board2Pdf, KiBot. |
| IPC | `api.enable_server: false`; no `/tmp/kicad` socket directory; probes refused. |
| Templates | KiCad user template dir `~/Documents/KiCad/10.0/template` contained only `default/`. |

## Phases

| # | Phase | Status |
| --- | --- | --- |
| 1 | Local repository audit | Done (above). |
| 2 | Architecture and test foundation | Done: `kicad_env`, `sexpr`, sandboxed test support, native fixture. |
| 3 | Environment installer | Done; run twice on this machine (second run: no changes). |
| 4 | Plugin manager | Done; IBOM, Freerouting, KiKit verified by headless invocation. |
| 5 | KiCad CLI and IPC adapters | Done; IPC live connection blocked (see below). |
| 6 | Native project templates | Done; three templates, installed into KiCad's user template dir. |
| 7 | Interactive project manager | Done (`project-manager.command`, `scripts/kit`). |
| 8 | Library and datasheet management | Done (library tables, component records). |
| 9 | Verification pipeline | Done (nine gates). |
| 10 | Manufacturing pipeline | Done (ten outputs, reproducibility, GO gate). |
| 11 | Integration tests | Done (see `docs/ACCEPTANCE_REPORT.md`). |
| 12 | Documentation and final audit | Done. |
| ++ | Template hardening (follow-up brief, milestones A–E) | Done: engineering guidelines (`docs/engineering/`), board profiles, portability and pin/pad gates, custom-library reference project and relocation tests, KiCad version policy, designator consistency, stale-export detection, extended manifest, three optional plugins catalogued. See below. |
| +++ | STM32 toolchain verification | Real cross-build verified with CubeMX 6.18 output and Arm GCC 15.3; four integration defects fixed; see ACCEPTANCE_REPORT. Hardware execution NOT_TESTED. |
| + | Thermal analysis, phase 1 (follow-up request) | Done: steady-state 2.5D estimate, `scripts/kit thermal`, optional `thermal` gate, analytic validation. Phases 2–3 (inner layers, I²R, transient/3D) open; see `docs/THERMAL_ANALYSIS.md`. |
| ++++ | PySide6 Desktop GUI & Test Suite | Done: PySide6 Desktop GUI (Dashboard, New Project, Projects, Verification, Manufacturing, Settings), `gui.command`, `scripts/gui.sh`, `scripts/kit gui`. 52 automated GUI tests passing in `qa/tests/test_gui.py`. Total test suite expanded to 205 tests (0 failures). |

## What was reused, replaced and moved

- **Reused and extended:** pinned CLI adapter and fail-closed release logic
  (approval binding, evidence copy, atomic publish), offline IBOM/PCM-ZIP
  installers, project registry, KiCad-generated blank files, macOS DMG
  installer, all original engineering READMEs and CSV contracts.
- **Replaced:** the single root template by three data-driven templates
  (`meta/templates/`); whole-repo copying by an explicit skeleton; ERC/DRC-only
  verification by nine gates; the comments-only `requirements.txt` by real pins.
- **Moved, bytes preserved:** project-level docs to `docs/project-template/`,
  the earlier kit docs and baseline inventory to `docs/archive/`, earlier QA
  reports and the 24 legacy tests to `qa/reports/archive/`, the board test-case
  README to `qa/project-template/tests/`. Reason: case-insensitive collisions
  with required docs and separation of kit and project content.
- **Not touched:** `meta/info.html`, `hardware/`/`components/`/`manufacturing/`
  originals, `LICENSE` (user edit), the old global venv, old QA run folders
  under `qa/generated/` (ignored by Git).

## Feature status

**Verified by automated tests on this machine** — see the acceptance report for
the run: layout and preservation, installer and idempotency, three templates
(KiCad loads all), name/path handling, CLI capability discovery, ERC/DRC on
genuine fixtures, all gates incl. negative cases, ten export outputs,
reproducibility, release blocking and GO path, component records, IPC failure
handling and config enabling (sandboxed), plugin status logic and headless
IBOM/Freerouting/KiKit invocation, firmware host tests and toolchain errors,
interactive manager sessions.

**Verified manually in this session** — real installer runs (first: venv,
templates CHANGED, three plugins VERIFIED; second: no changes); live
`ipc status` diagnosis; PlatformIO 6.1.18 AVR build of the Arduino template
firmware in an isolated scratch environment (`firmware.hex`, 1,160 bytes flash).

**Not verified / requires manual checks**
- KiCad GUI: opening generated projects and selecting templates in **New
  Project from Template** (not exercised, to avoid disturbing the running
  KiCad session). KiCad's CLI and pcbnew load every generated project.
- KiBuzzard and Board2Pdf (not installed; GUI-only verification).
- STM32 target build: verified later in this session with real CubeMX output (see ACCEPTANCE_REPORT, "STM32 toolchain verification"); hardware execution not tested.
- Flashing hardware, electrical, thermal and prototype validation (out of scope
  of tooling; never claimed).

## Blockers

| Blocker | Impact | Resolution |
| --- | --- | --- |
| KiCad API server disabled while KiCad runs | No live IPC connection or board queries could be tested; the live test is skipped. | Enable **Preferences > Plugins > Enable KiCad API** and restart KiCad, or quit KiCad and run `scripts/kit ipc enable --apply`; then `scripts/kit ipc status`. |
| No Arm GNU toolchain / CubeMX project | STM32 cross-build unverified. | Install the toolchain, generate CubeMX output, run `scripts/kit firmware PROJECT --target stm32`. |
| PCM has no CLI | Recommended plugins cannot be installed unattended. | Guided steps: `scripts/kit plugins guide NAME`. |

## Template hardening (milestones A–E)

**A – Assessment.** Baseline 127 tests passing. Gaps found: no engineering
guidelines; one blank board configuration (no stack-up, rules or net classes);
no check for absolute paths or symbol/footprint pin mismatches; no project with
project-local libraries or relocation test; any non-10.0.7 KiCad simply refused;
exports could not be checked for staleness; BOM/placement designators not
cross-checked; brief's three extra plugins absent.

**B – Documentation.** `docs/engineering/`: workflow index, component selection,
datasheet-review checklist, schematic, placement, routing (constraints vs
heuristics), manufacturing with readiness checklist, lessons learned (14
scenarios from the brief + 1 additional). Copied into every project.

**C – Template reliability.** Board profiles `2-layer` / `4-layer`
(`meta/templates/profiles/`, defaults authored by pcbnew, read back in tests);
`--profile` for create and the menu; title block with `${PROJECTNAME}`;
`portability` and `pin_pad_mapping` gates; `qa/fixtures/custom-lib` reference.

**D – Validation and release.** Version policy (`KICAD_KIT_ALLOW_UNTESTED`,
UNTESTED marking, GO block); designator consistency in exports; manifest
records configuration and known limitations; `scripts/kit releases` status.
Bug fixed on the way: firmware build output was hashed as source.

**E – Audit.** Full suite, clean-directory runs of all documented commands,
installer idempotency, documentation link and command tests.

Remaining: GUI and live IPC unverified; a four-layer *reference board* is
deliberately not provided (no circuit needs it); the source tutorial was not
available, so lessons describe failure modes without tutorial specifics.
