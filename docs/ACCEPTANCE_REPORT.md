# Acceptance report

Date 2026-10-18 · kit 2.0.0 · KiCad 10.0.7 · macOS 26.6.2 arm64 · Python 3.13.5.
Evidence is from this machine; nothing below is inferred from documentation.

## Test run

```text
$ python3 test_template.py -v
Ran 151 tests in ~165 s
OK (skipped=1)
```

The one skip is `test_ipc.IpcLiveTests.test_live_connection_and_queries`:
"no reachable KiCad IPC server: API server disabled ... (api.enable_server=False)".
Native KiCad tests ran (KiCad 10.0.7 detected); none were disabled. With
`KICAD_NATIVE_TESTS=0` the same suite passes offline in ~8 s with 38 native
tests skipped, which is how it behaves on a machine without KiCad.

## Completion criteria

| Criterion | Result | Evidence |
| --- | --- | --- |
| Existing structure preserved | Met | `test_layout`: mandatory entries; every original file from the baseline inventory is byte-identical in place or at its recorded relocation, except the listed intentional edits. |
| KiCad 10.0.7 supported | Met | Exact-version guard (exit 11 for 9.0.4/10.0.6/11.0.0/nightly fakes); 43 CLI commands discovered from the installed binary. |
| Installation repeatable | Met | Real run 1: venv and templates `CHANGED`; real run 2: `changed=[]`; `test_installer` asserts no file is rewritten and foreign dirs survive. |
| Plugin status verifiable | Met | Real headless runs: InteractiveHtmlBom 2.12.0 → HTML BOM; Freerouting 2.4.1 (Java 27) → routed SES; KiKit 1.8.1 → 2×2 panel. KiBuzzard, Board2Pdf, KiBot reported `NOT_INSTALLED` with guided steps. |
| IPC diagnostics accurate | Met (live connection blocked) | Correct root cause found (`api.enable_server=false`, no socket, KiCad PID 7129, refused probe); failure classes and safe enabling tested in a sandbox. |
| Three templates functional | Met | All generate with paths containing spaces; kicad-cli ERC and pcbnew `LoadBoard` succeed on each; installed into `~/Documents/KiCad/10.0/template`. |
| Interactive project creation | Met | Scripted manager sessions create projects, retry invalid names, cancel, refuse occupied destinations; `.command` launcher tested. |
| Generated projects open in KiCad | Partly | Loaded by kicad-cli and pcbnew. The GUI was not driven, to avoid disturbing the running KiCad session. |
| ERC/DRC on genuine fixtures | Met | `qa/fixtures/divider` (official libraries only): 0 ERC, 0 DRC, 0 unconnected, 0 parity; negative variants fail as expected. |
| Manufacturing exports work | Met | Ten outputs complete; two runs identical across 38 normalized artifacts; existing revisions refused; release blocked without authorization, Git or passing gates. |
| Tests pass | Met | 151 run, 0 failures, 1 skip (above). |
| Thermal estimate (follow-up) | Met for phase 1 | Analytic benchmarks (two-node exact, 1D fin within 1 %), grid convergence, energy balance, pad positions identical to pcbnew; outputs PNG/HTML/CSV/NPZ. Absolute accuracy for real boards not validated (needs measurement). |
| Documentation accurate | Met | 12 required docs; a test checks every `scripts/kit <cmd>` in README, AGENTS and docs exists. |
| No unverified claims | Met | Manual/unverified items listed below; drafts are always NO-GO. |
| No Git writes | Met | Only `git status/diff/log/ls-files/remote/branch/rev-parse` used on this repository. Tests use `git init` only in temporary projects and assert no commit exists. |

## Verified outside the automated suite

- PlatformIO 6.1.18 (isolated scratch install, `PLATFORMIO_CORE_DIR` in scratch):
  Arduino Shield firmware built for `uno` → `firmware.hex`, RAM 35 B, flash 1,160 B;
  `app/src/heartbeat.c` and `bsp/arduino/bsp_arduino.cpp` compiled into it.
- `scripts/kit ipc status` / `ipc enable` against the real configuration (exit 3 / 16).
- `scripts/kit plugins updates` against the live PCM repository (index SHA-256 checked).

## Not verified (manual follow-up)

1. Live IPC connection and board queries — enable the API (`docs/KICAD_IPC.md`).
2. KiCad GUI: template dialog listing and opening generated projects.
3. STM32 cross-build — needs `arm-none-eabi-gcc` and an STM32CubeMX project.
4. KiBuzzard, Board2Pdf (GUI plugins, not installed) and KiBot (not installed).
5. Any electrical, thermal, mechanical or prototype validation — outside tooling.

## Quality scores

| Category | Score | Evidence | Gap to 10 |
| --- | --- | --- | --- |
| Maintainability | 8.5 | One core behind CLI, menu and wrappers; `tools/` split into responsibility packages with downward-only dependencies; one path module; data-driven templates; module docstrings. | No static typing/linting config; `tools/cli/main.py` dispatch and `release/exports.export_project` are long. |
| Reliability | 8.5 | Fail-closed exit codes, atomic staging, lock and source-change detection, idempotent installs, negative tests for every gate. | GUI paths and live IPC untested; STEP reproducibility uses a structural census. |
| Portability | 8 | All paths overridable; spaces in paths tested; no hard-coded user names; KiCad located in `/Applications` or `~/Applications`. | macOS only by design and pinned to KiCad 10.0.7; Linux code paths exist but are untested. |
| Automation | 9 | Every function non-interactive with `--json` and documented exit codes; one-command install; reproducible exports with comparison. | PCM installs need the GUI (no PCM CLI exists). |
| Verification quality | 9 | 151 tests incl. real KiCad ERC/DRC/exports, real plugin invocations, real firmware compiles, injected-defect tests; nothing mocked where KiCad is available. | No live IPC or GUI test; no STM32 target build. |

Scores were not raised to reach a target; each gap above is real and listed
with what would close it.

## Template hardening (engineering best practices), 2026-10-18

Baseline before the hardening work: 127 tests, 0 failures, 1 skipped.
After: **149 tests, 149 run, 148 passed, 0 failed, 1 skipped, 0 blocked**
(skipped: live IPC test, API server disabled). Without KiCad
(`KICAD_NATIVE_TESTS=0`): 149 run, 112 passed, 37 skipped.

### Criteria

| # | Criterion | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Existing functionality intact | Met | All 127 baseline tests still pass (2 expectations updated for new behaviour: menu profile prompt, plugin tier set). |
| 2 | Previously passing tests pass | Met | As above. |
| 3 | New behaviour tested | Met | `test_hardening.py` (20), manufacturing (+2); see `docs/VERIFICATION.md`. |
| 4 | Generated projects open in KiCad | Partly | kicad-cli ERC/DRC and pcbnew load every template and profile; KiCad GUI not driven (running session left untouched). |
| 5 | Portable library references | Met | `portability` and `library_references` gates; `custom-lib` reference passes before and after relocation to a non-ASCII path with spaces. |
| 6 | Documentation matches implementation | Met | Commands in README/docs executed in a clean directory; tests check CLI names and relative links. |
| 7 | Engineering practices documented | Met | `docs/engineering/` (7 documents, copied into every project). |
| 8 | Reference projects with transparent status | Met | `qa/fixtures/README.md`. |
| 9 | Reproducible manufacturing outputs | Met | Normalized-digest comparison; STALE/MODIFIED detection. |
| 10 | No agentic/unrelated infrastructure | Met | None added. |
| 11 | No unverified compatibility claims | Met | New plugins listed as *declared* compatible, GUI-only verification. |
| 12 | Nothing staged/committed/pushed | Met | Read-only Git commands only. |

### KiCad compatibility report

Detected: `kicad-cli` 10.0.7 at `/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli`
(status TESTED), bundled Python 3.9.13 with pcbnew 10.0.7. Real integration
tests performed: ERC/DRC/parity on both reference projects, every template and
both profiles; profile read-back and rebuild through pcbnew; pad positions
against pcbnew; relocation; all export types, reproducibility, designator
consistency and release status; IBOM, Freerouting and KiKit invocations; thermal
cross-check. Not performed: GUI, live IPC.

### Quality assessment (0–10)

| Area | Score | Evidence | Main gap |
| --- | --- | --- | --- |
| Repository architecture | 8.5 | Layered `tools/` packages with an enforced import test; data-driven templates and profiles | Long CLI dispatch module |
| Reusability | 8.5 | Three templates × profiles; guidelines and checklists copied into every project | Only two board profiles; no hierarchical schematic starter |
| Portability | 8.5 | `${KIPRJMOD}` libraries, portability gate, relocation test with non-ASCII path | macOS only by design |
| KiCad compatibility | 8.5 | Exact version pin, explicit UNTESTED mode, capability discovery, version facts documented | Only 10.0.7 tested; GUI/IPC untested |
| Library management | 8 | Resolution incl. nested tables, pin/pad check, 3D-model and portability gates, attribution example | Pad geometry and model accuracy need manual review |
| Engineering documentation | 8.5 | Constraint/heuristic labelling, checklists, 14+1 lessons with checks | Tutorial not available; lessons describe failure modes generally |
| Test coverage | 9 | 149 tests incl. real KiCad, negative cases for every gate | No GUI or live IPC tests |
| Manufacturing preparation | 8.5 | Complete package, manifest with config/limits, stale detection, designator consistency, fail-closed GO | No fabricator-specific presets (deliberately) |
| Maintainability | 8.5 | Small modules, shared skip rules, builders for fixtures/profiles | No type checking/linting configuration |
| User experience | 8 | One installer, menu and CLI with JSON, troubleshooting table | English kit docs vs. German README; GUI template dialog unverified |

## Final acceptance and usability validation, 2026-10-18

### Verdict: **CONDITIONAL**

All ten automated acceptance criteria below are met with evidence. The KiCad
GUI gate is **NOT_TESTED** (no safe GUI automation in this environment; opening
KiCad windows on the developer's desktop was not done). Acceptance becomes
**ACCEPTED** when `docs/GUI_ACCEPTANCE.md` is completed with all checks PASS.

| # | Criterion | Status | Evidence |
| --- | --- | --- | --- |
| 1 | Mandatory automated tests pass | PASS | 151 run, 150 passed, 0 failed, 1 skipped (optional live IPC) |
| 2 | Project creation outside the checkout | PASS | Default, 2-layer, 4-layer, custom-library projects created in `…/acceptance 验收 Prüfung/`; no reference to the checkout inside them |
| 3 | Generated files portable | PASS | Projects moved to `…/relocated – 移動 Ω/` and `…/verschoben ✓/` pass library, portability and pin/pad gates |
| 4 | Board profiles correct | PASS | pcbnew read-back: 2-layer → 2 Cu, min track 0.15; 4-layer → 4 Cu, min track 0.1, stack-up present; net classes Default/Power |
| 5 | Library references resolve | PASS | `libraries check`: 224 symbol / 156 footprint libraries incl. project-local, 0 broken; registration idempotent |
| 6 | Installation reproducible | PASS | Fresh copy (216 files) installed into isolated dirs incl. `.venv` from PyPI; real install: update → `UPDATED`, rerun → `UNCHANGED` |
| 7 | Engineering documentation accurate | PASS | Reviewed; corrected CAN differential-pair claim and two over-statements about release behaviour |
| 8 | Manufacturing release checks functional | PASS | Real export → CURRENT; board edit → STALE (`divider.kicad_pcb` listed); new export CURRENT; designator consistency COMPLETE |
| 9 | No unexplained files | PASS | 214 untracked files classified (below); tests add no files; generated output ignored, including nested projects |
| 10 | No unresolved mandatory failures | PASS | — |
| — | KiCad GUI | **NOT_TESTED** | Manual checklist: `docs/GUI_ACCEPTANCE.md` |
| — | Live IPC | **NOT_TESTED** (optional) | API server disabled; diagnosis exact |

### Exact test results

| Run | Collected | Passed | Failed | Skipped | Skip reason |
| --- | --- | --- | --- | --- | --- |
| With KiCad 10.0.7 | 151 | 150 | 0 | 1 | Live IPC: KiCad not running, `api.enable_server=false` |
| `KICAD_NATIVE_TESTS=0` | 151 | 113 | 0 | 38 | 37 need KiCad 10.0.7, 1 live IPC |

Real KiCad tests executed: 37 (ERC/DRC/parity, exports, reproducibility,
profiles via pcbnew, pad positions, relocation, plugin invocations, template
loading). `git diff --check`: clean.

### Defects found and fixed in this phase

1. `.gitignore` patterns were root-anchored: verifying/exporting inside a nested
   project (e.g. `qa/fixtures/divider`) would have left untracked output → `**/` patterns added.
2. Firmware host build failed after moving a project (CMake cache keeps the
   absolute source path) → stale cache detected, reconfigured with `--fresh`; regression test.
3. Projects created through KiCad's template dialog got a README titled with the
   template id → neutral heading for installed templates; test.
4. `verify` summary did not say *why* a gate failed → finding types and an
   outline hint are shown.
5. Documentation: CAN differential-pair claim corrected; stale-export and
   GO-approval statements made exact; first-design walkthrough, update
   procedure and GUI checklist added.

### Remaining defects and risks

- GUI not verified (see verdict). Live IPC not verified.
- Installed KiCad templates always use the `2-layer` profile (KiCad cannot pass
  options to a template); documented in README step 2.
- STM32 cross-build untested (no Arm toolchain/CubeMX project).
- Pad geometry and 3D-model accuracy remain manual review items.

### Untracked-file classification (214)

| Files | Class |
| --- | --- |
| 41 | Kit source code (`tools/`) |
| 18 | Entry points and shell wrappers |
| 14 | Automated tests |
| 15 | Reference projects and builder (`qa/fixtures/`) |
| 13 | Templates, profiles, KiCad metadata (`meta/`) |
| 8 | Native KiCad defaults (`hardware/native-defaults/`) |
| 15 | Firmware templates |
| 15 → 16 | Kit documentation (`docs/*.md`; `GUI_ACCEPTANCE.md` added in this phase) |
| 8 | Engineering guidelines |
| 46 | Project skeleton content copied into projects |
| 4 | Repository policy/config |
| 17 | Archive: superseded docs and the earlier 24-test suite (historical; owner may delete) |

No generated artifacts, editor state, caches or virtual environments are among them.

### Quick start

```sh
./install_template.command                                   # once; again after updates
./project-manager.command                                    # or:
scripts/kit create --template generic-pcb --profile 2-layer --name "My Board" --dest "$HOME/Projects/My Board"
scripts/kit open    "$HOME/Projects/My Board"
#   design in KiCad: schematic + fields, F8 update PCB, outline on Edge.Cuts, place, route, save
scripts/kit verify  "$HOME/Projects/My Board"
scripts/kit export  "$HOME/Projects/My Board" --revision A1
scripts/kit releases "$HOME/Projects/My Board"
```

### Recommended next actions

1. Run `docs/GUI_ACCEPTANCE.md` once (about 15 minutes) and record the result.
2. Optionally enable the KiCad API to let the live IPC test run.
3. Decide whether the `docs/archive/` and `qa/reports/archive/` history should be committed.

## STM32 toolchain verification, 2026-10-18

Overall acceptance status remains **CONDITIONAL** (KiCad GUI gate NOT_TESTED).

| Item | Status | Evidence |
| --- | --- | --- |
| STM32CubeMX installation | **VERIFIED** (installed, not driven) | `/Applications/STMicroelectronics/STM32CubeMX.app`, version 6.18; STM32Cube_FW_F1 V1.8.7 in `~/STM32Cube/Repository` |
| CubeMX code generation by the kit | NOT_TESTED / not a kit function | Headless `-q` regeneration from a copy of the user's `.ioc` hung at "IP not ready for code generation: I2C2"; the kit does not run CubeMX |
| Arm GNU compiler | **VERIFIED** | Arm GNU Toolchain 15.3.Rel1 (`arm-none-eabi-gcc` 15.3.1) in `~/Tools/arm-gnu/…` and `~/.local/toolchains/…`, not on PATH; found by the new discovery |
| CMake / Ninja / OpenOCD | present | CMake 3.31.2, Ninja 1.13.2, OpenOCD 0.12.0 (OpenOCD not used by the kit) |
| Firmware cross-build | **VERIFIED** | Template `stm32-embedded` project + CubeMX 6.18 output of an existing STM32F103C8 project (copied read-only; user's own `app.c` excluded; USER CODE wired to `bsp_heartbeat_task()`), label `LED_USER`: `firmware.elf` ELF32 ARM, EABI5 soft-float, Tag_CPU_name 7-M / Thumb-2; text 40,732 B, data 380 B, bss 6,700 B; FLASH 41,112 B / 64 KB (62.73 %), RAM 7,080 B / 20 KB (34.57 %); `main` calls `bsp_heartbeat_task`, `heartbeat_init/poll` linked |
| Rebuild after relocation | **VERIFIED** | Project moved to a Unicode path; stale CMake cache reconfigured; same memory usage |
| No contamination | **VERIFIED** | All builds in temporary directories; untracked files in the repository unchanged (215) |
| Firmware hardware execution | **NOT_TESTED** | No flashing or measurement performed |
| KiCad GUI | **NOT_TESTED** | Manual checklist `docs/GUI_ACCEPTANCE.md` outstanding |

### Defects found and fixed

1. **STM32 integration failed against real CubeMX output** (configure error
   `Cannot specify sources for target "firmware" which is not built by this
   project`): the executable is now created as `${CMAKE_PROJECT_NAME}` before
   the generated `stm32cubemx` package is added.
2. **Linker script not found**: CubeMX's toolchain file uses
   `${CMAKE_SOURCE_DIR}/<script>.ld`; the path is redirected to
   `bsp/stm32/cubemx/` without editing generated files.
3. **Installed Arm toolchain reported missing**: discovery via
   `ARM_GNU_TOOLCHAIN_BIN`, PATH and standard locations (newest version), PATH
   changed only for the build subprocess; actionable message when absent.
4. **Hard-coded `STATUS_LED` label**: configurable `FW_STATUS_LED` preset
   variable.
5. The STM32 build now reports ELF architecture and FLASH/RAM usage;
   `scripts/kit doctor` lists the optional STM32 tools.

### Test results after this work

| Run | Collected | Passed | Failed | Skipped |
| --- | --- | --- | --- | --- |
| Default (KiCad 10.0.7) | 157 | 155 | 0 | 2 (live IPC; opt-in STM32 cross-build) |
| With `KIT_STM32_CUBEMX_SOURCE` set | 157 | 156 | 0 | 1 (live IPC) |
| `KICAD_NATIVE_TESTS=0` | 157 | 118 | 0 | 39 |

Remaining acceptance blockers: KiCad GUI checklist (mandatory). Live IPC and
STM32 hardware execution remain optional, NOT_TESTED.
