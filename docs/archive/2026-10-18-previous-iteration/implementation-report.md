> Historischer Bericht der ersten Implementierung. Den aktuellen Stand nach
> Dokumentationsbereinigung und Diagnosekorrekturen beschreibt
> [project-summary.md](project-summary.md). Frühere ZIPs sind Momentaufnahmen.

# Implementation report

Extended the existing root in place. No original path was renamed, moved, merged or deleted. `README Kopie.md`, `AGENTS.md`, `meta/info.html`, all original engineering documents/CSVs and the license remain byte-for-byte unchanged. Existing uncommitted work was inventoried before narrow edits; nothing was staged or committed.

The root-as-template architecture remains intact. No parallel top-level application/template directory was introduced. New implementations belong to `tools/`; shell entrypoints belong to `scripts/`. Global companion state stays outside projects.

## Repairs and compatibility

The installer and old tests referenced an absent `embedded-hw-fw/` child. They now use the actual root. The `.command` remains executable, supports the original prompt, and also accepts `--parent`. Identical reinstalls verify hashes and preserve extra files. Changed/conflicting installations stop without overwriting. `tools/verify.sh` delegates to the reusable CLI while retaining default root behavior, verification exit 20, and setup exit codes 10/11/12/13. The macOS DMG installer retains its options and fixes quoting for paths with spaces. The plugin entrypoint retains default InteractiveHtmlBom behavior and `--dest`/`--source`.

## Implemented capabilities

- Central plugin catalog, global diagnostics, pinned InteractiveHtmlBom checkout and checksum/metadata-checked manual PCM-ZIP installation for FreeRouting or InteractiveHtmlBom. PCM-managed packages remain owned by PCM.
- KiCad 10.0.7 CLI adapter, real read-only IPC ping/version diagnostics, optional global Python environment with tested dependency lock, native template installation and interactive project creation.
- Portable generated domain trees, root native design files from authentic KiCad defaults, optional Git initialization/global project registry, KiCad/VS Code opening and conservative local library tables.
- ERC/DRC including schematic parity, structured report validation, source hashes, independent source-change checks and unique run logs.
- BOM, Gerber, Excellon drill, placement and STEP exports, revision manifests, artifact hashes, NO-GO drafts, and fail-closed reviewed release gates.
- Optional STM32/CMake and Arduino adapters require actual vendor projects/cores; generic PCB use has no firmware dependency.

## Actual validation

Five legacy checks passed. All 22 regression/integration tests passed with `KICAD_NATIVE_TESTS=1`. Tests cover mandatory root entries, preserved original files, repeat install and extra-file preservation, source conflicts, paths with spaces, unsafe paths/symlinks, generated project contracts, plugin archive checks/repeat install, registry isolation, Git initialization without commit, lock refusal, optional firmware refusal before target setup, version mismatch, approval bindings and exclusions blocking the gate.

Native KiCad 10.0.7 was exercised independently of existence checks: blank-project ERC/DRC produces the expected invalid-outline failure; a mechanical-only board created by the actual pcbnew API passes ERC/DRC and parity; all five export categories succeed; a malformed schematic fails. Positive fixtures remain NO-GO drafts. Native source hashes stay unchanged during verification. Evidence is in `qa/generated/native-integration/`, with portable summary and artifact hashes in `qa/reports/toolchain-validation.json`. Shell syntax, old entrypoint execution and whitespace checks also passed.

The native GUI recognized the installed template and instantiated an independent project with the domain directories and matching root design files. KiCad intentionally omits the template metadata directory from GUI-created designs. The CLI path was separately exercised using a project path with spaces.

The optional IPC client and its actual dependencies installed successfully into an isolated `/tmp` environment. A live API connection was refused; diagnostics correctly reported UNAVAILABLE. No connected IPC success is claimed. The VS Code launcher returned exit zero but emitted an Electron permission message; visual editor state is not asserted. Existing PCM plugin directories were detected; no production plugins were replaced or executed.

## Limits and review ownership

A clean-machine DMG installation was not performed because 10.0.7 is already installed. Production plugin execution, real MCU builds/flashing and electrical/physical prototype tests were not performed. A passing mechanical fixture is not a validated circuit. Human reviewers must supply real signed checklist/prototype evidence; the software checks evidence bindings/existence, not signature authenticity or measurement truth. Disabled native checks are visible in reports and require manual review. Archive installation supports legacy plugin payloads only; additional runtimes/libraries and IPC plugin registration use KiCad PCM.

## Existing files extended

| File | Extension |
| --- | --- |
| `.gitignore` | Appended generated QA/manufacturing, Python environment and cache exclusions. |
| `README.md` | Corrected root source description and added command/onboarding links and test instructions. |
| `install_template.command` | Repaired source path through module delegation; retained Finder interaction and executable mode. |
| `requirements.txt` | Retained comments-only pip compatibility; documented optional kit/runtime requirements. |
| `scripts/install-kicad.sh` | Preserved installer, corrected quoted CLI path expansion. |
| `scripts/install-plugins.sh` | Delegates legacy options and new plugin capabilities to the central plugin manager. |
| `test_template.py` | Repaired root path; handles actual generated project triples and native GUI metadata omission. |
| `tools/verify.sh` | Backward-compatible wrapper around reusable verification logic. |

## Every added source file

| File | Purpose |
| --- | --- |
| `.gitattributes` | Text/binary treatment and LF endings for portable native and executable source. |
| `docs/baseline-inventory.json` | Pre-edit inventory, original hashes, modes and existing Git changes. |
| `docs/baseline.md` | Audit findings, reusable functionality and preservation decisions. |
| `docs/conventions.md` | Project conventions documentation. |
| `docs/development-kit.md` | Development kit architecture and commands documentation. |
| `docs/implementation-report.md` | This report, complete source tree and per-file extension record. |
| `docs/installation.md` | Installation and scope documentation. |
| `docs/ipc.md` | IPC setup and diagnostics documentation. |
| `docs/manufacturing-workflow.md` | Verification and manufacturing workflow documentation. |
| `docs/plugins.md` | Global plugin management documentation. |
| `docs/troubleshooting.md` | Troubleshooting documentation. |
| `firmware/tools/workflows.md` | Optional firmware workflows documentation. |
| `hardware/native-defaults/README.md` | Native blank defaults documentation. |
| `hardware/native-defaults/default.kicad_pcb` | Authentic blank PCB generated by KiCad Manager 10.0.7; no fabricated design. |
| `hardware/native-defaults/default.kicad_pro` | Authentic blank project settings generated by KiCad Manager 10.0.7. |
| `hardware/native-defaults/default.kicad_sch` | Authentic blank schematic generated by KiCad Manager 10.0.7; per-project UUID renewal. |
| `manufacturing/approval.example.json` | NO-GO approval skeleton with explicit review gates and evidence fields. |
| `qa/design-reviews/review-template.txt` | Review findings, responsibilities, evidence and explicit NO-GO default. |
| `qa/reports/toolchain-validation.json` | Measured test outcomes, fixture artifact hashes and explicit validation limits. |
| `qa/reports/validation-scope.md` | Validation scope documentation. |
| `qa/tests/test_native.py` | Opt-in genuine KiCad ERC/DRC, API fixture generation and export integration tests. |
| `qa/tests/test_regressions.py` | Mandatory structure, preservation, idempotence, collision and portability tests. |
| `qa/tests/test_tools.py` | Plugin payload, Git/registry, lock, approval, malformed-report and firmware selection tests. |
| `scripts/configure-kicad.sh` | Template-path configuration wrapper; delegates to reusable tools modules. |
| `scripts/create-project.sh` | Interactive/noninteractive independent project creator; delegates to reusable tools modules. |
| `scripts/diagnose.sh` | Environment diagnostic wrapper; delegates to reusable tools modules. |
| `scripts/export-manufacturing.sh` | Draft and gated release export wrapper; delegates to reusable tools modules. |
| `scripts/firmware-build.sh` | Optional real-target firmware build wrapper; delegates to reusable tools modules. |
| `scripts/install-environment.sh` | Optional global IPC environment installer; delegates to reusable tools modules. |
| `scripts/install-template.sh` | Template registration wrapper; delegates to reusable tools modules. |
| `scripts/manage-libraries.sh` | Project-local library registration wrapper; delegates to reusable tools modules. |
| `scripts/open-project.sh` | KiCad/VS Code project launcher; delegates to reusable tools modules. |
| `scripts/package.sh` | Portable source ZIP wrapper; delegates to reusable tools modules. |
| `scripts/verify.sh` | Pinned ERC/DRC verification wrapper; delegates to reusable tools modules. |
| `tools/__init__.py` | Reusable development-kit modules. No global installation at import time. |
| `tools/common.py` | Safe filesystem operations and audit records. |
| `tools/environment.py` | Optional global Python environment and environment/configuration diagnostics. |
| `tools/firmware.py` | Optional build adapters; never invent board pinouts or vendor startup code. |
| `tools/ipc.py` | Read-only IPC diagnostics, isolated from the optional kipy dependency. |
| `tools/kicad_cli.py` | Pinned KiCad subprocess adapter and auditable read-only verification. |
| `tools/kit.py` | Stable CLI behind repository shell entrypoints. |
| `tools/libraries.py` | Conservative project-local symbol/footprint library registration. |
| `tools/packaging.py` | Distributable source ZIP, including hidden policy files but no tool binaries. |
| `tools/plugins.json` | Central plugin identity, upstream and selected-version catalog. |
| `tools/plugins.py` | Machine-global plugin management; never edits PCM's database. |
| `tools/registry.py` | Machine-local project index; never copied into designs. |
| `tools/release.py` | Draft exports and fail-closed manufacturing approval gates. |
| `tools/requirements-ipc-lock.txt` | Tested transitive dependency resolution for optional IPC environment. |
| `tools/requirements-ipc.txt` | Optional pinned direct IPC client dependency. |
| `tools/template_engine.py` | One source template, conservative copying, no global dependencies. |

## Final source directory tree

OS metadata, `.git/`, caches and generated run artifacts are retained where present in the workspace but omitted here and from the distributable source ZIP. The generated archive preserves executable modes. The full initial workspace inventory is in `baseline-inventory.json`.

```text
PCB-Project-Template/
  .gitattributes
  .gitignore
  AGENTS.md
  LICENSE
  README.md
  components/
    README.md
    approved-parts/
      README.md
    bom_master.csv
    datasheets/
      README.md
    sources.csv
    spice-models/
      README.md
  docs/
    architecture.md
    baseline-inventory.json
    baseline.md
    bringup.md
    conventions.md
    decisions/
      ADR-0001-repo-boundaries.md
    development-kit.md
    implementation-report.md
    installation.md
    interfaces.md
    ipc.md
    manufacturing-workflow.md
    plugins.md
    requirements.md
    troubleshooting.md
    verification-plan.md
  firmware/
    README.md
    app/
      README.md
    bsp/
      README.md
    config/
      README.md
    drivers/
      README.md
    tests/
      README.md
    tools/
      README.md
      workflows.md
  hardware/
    README.md
    constraints/
      README.md
    interfaces/
      README.md
      pinmap.csv
      power_budget.csv
    libraries/
      3d-models/
        README.md
      README.md
      footprints/
        README.md
      symbols/
        README.md
    mechanical/
      README.md
    native-defaults/
      README.md
      default.kicad_pcb
      default.kicad_pro
      default.kicad_sch
    simulations/
      README.md
  install_template.command
  manufacturing/
    README.md
    approval.example.json
    assembly/
      README.md
    fabrication/
      README.md
    releases/
      RELEASE_CHECKLIST.md
  meta/
    info.html
  qa/
    README.md
    design-reviews/
      README.md
      review-template.txt
    reports/
      README.md
      toolchain-validation.json
      validation-scope.md
    tests/
      README.md
      test_native.py
      test_regressions.py
      test_tools.py
  requirements.txt
  scripts/
    configure-kicad.sh
    create-project.sh
    diagnose.sh
    export-manufacturing.sh
    firmware-build.sh
    install-environment.sh
    install-kicad.sh
    install-plugins.sh
    install-template.sh
    manage-libraries.sh
    open-project.sh
    package.sh
    verify.sh
  test_template.py
  tools/
    __init__.py
    common.py
    environment.py
    firmware.py
    ipc.py
    kicad_cli.py
    kit.py
    libraries.py
    packaging.py
    plugins.json
    plugins.py
    registry.py
    release.py
    requirements-ipc-lock.txt
    requirements-ipc.txt
    template_engine.py
    verify.sh
```

Source ZIP creation: `./scripts/package.sh --output /tmp/PCB-Project-Template-extended.zip`. The packager refuses existing outputs and excludes global dependencies, Git internals, transient OS files and generated outputs. ZIP/extracted-copy checks are recorded in the adjacent external validation record.

## Subsequent user-authorized cleanup

The preservation statements above describe the initial implementation. After
review, the user authorized removal of `README Kopie.md`. Its useful onboarding
content is now in `README.md`; conventions and preservation tests were updated.
The initial baseline inventory remains historical. The directory listing above
reflects removal of the duplicate; previously generated ZIPs are older snapshots.
