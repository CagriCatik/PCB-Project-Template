# Rules for Codex / Claude / other agents

## Architecture invariants

1. A single KiCad 10.0.7 project per generated repository by default; core
   `.kicad_pro`, `.kicad_sch`, `.kicad_pcb` at the repository root.
2. Hardware truth lives in the schematic, board and verified part datasheets;
   the pinmap is a reviewed interface artifact, not a second independent truth.
3. Keep firmware HAL/BSP separated from application logic. Do not insert target-
   specific dependencies into platform-independent application code.
4. KiCad custom libraries are local and referenced via `${KIPRJMOD}`.
5. Generated outputs and external tools are not source files. No hand-editing
   of Gerbers, drill files, position files, PDFs or ERC/DRC reports.

## Mandatory toolchain

- KiCad **10.0.7** is required for native design edits, ERC/DRC,
  snapshots, renders and accepted verification evidence. Confirm it with
  `scripts/kit version` before native work; use `scripts/kit doctor` when
  environment diagnostics are needed.
- Never use `KICAD_KIT_ALLOW_UNTESTED=1` to bypass this requirement for design
  work or validation. If the required version is absent, continue independent
  source/docs/unit-test work and report native checks as blocked or skipped.
  Do not claim support based on another installed KiCad version.

## Use the implemented tools where they fit

Run these commands from the kit checkout, supplying the target project's path.
Inspect command `--help` and existing modules before inventing parallel scripts.
Do not run unrelated tools just to fill a checklist.

| Work | Existing tool to use |
| --- | --- |
| Environment/version | `scripts/kit version`, `scripts/kit doctor` |
| Presentation-only schematic changes | `scripts/kit schematic snapshot` before; `compare` after |
| Schematic readability review | `scripts/kit schematic review` with functional detail views; inspect all images; `lint` provides hints only |
| Reusing earlier review evidence | `scripts/kit schematic status` to detect stale sources/modified artifacts |
| ERC, DRC, parity, footprints, pin/pad, metadata | `scripts/kit verify PROJECT` (use `--gate` for a scoped check) |
| Component/library records | `scripts/kit components validate PROJECT`, `scripts/kit libraries check PROJECT` |
| Carrier/socket design | `scripts/kit carrier check PROJECT` for complete pin inventory, plus native pin/pad and schematic review |
| Supply states, connectors and HW/FW declarations | `scripts/kit contracts check PROJECT`; add a current `--snapshot` for native pin/net checks |
| Electrical inputs and static budgets | `scripts/kit assumptions check PROJECT`, `scripts/kit power-budget calculate PROJECT` |
| Firmware work | `scripts/kit firmware PROJECT --target TARGET` when the target/toolchain applies |
| Thermal work | `scripts/kit thermal analyze PROJECT` only with documented loss estimates |
| Manufacturing | `scripts/kit export PROJECT --revision REV` for drafts; existing GO authorization/checklist remains mandatory |

A hint, semantic match or unchanged finding count is not visual approval.
Record real commands, versions, exit codes, evidence hashes and limitations.
Native files remain the source of truth. Extend the responsible module if an
existing tool lacks a needed capability; avoid duplicate implementations.

## Before changing native KiCad files

- Check KiCad version **10.0.7** and project revision; detect any live editing
  session before scripted writes. Never overwrite open designer state.
- Use actual KiCad APIs/CLI; do not fabricate a passing report or pretend that
  IPC is available when the socket cannot be contacted.
- Make small, auditable changes; re-run validation and log command/version,
  exit code, artifact hashes and differences.
- Do not create dummy 3D models in place of actual vendor STEP/STL models.
- Always mark calculations as estimates; thermal, electrical and mechanical
  estimates do not replace measurement/prototype testing.

## Power and interface changes

- Follow `docs/engineering/design-contracts.md`. Update operating states,
  connector contracts, pinmap and BSP binding declarations together when pins,
  polarity, inversion, supply sources or default/fault behaviour change.
- Use the shared assumptions register; distinguish guaranteed, typical,
  assumed and measured inputs with source/revision/conditions. Never turn a
  typical curve or a calculation into a guaranteed limit or a measurement.
- Budget common paths with total current and branch paths with branch current;
  state the physical voltage endpoint. Check explicit normal/stall/no-load
  scenarios and document model limits and prototype measurements still needed.
- Check USB-only, combined supplies, reset, bootloader, missing module, brownout
  and battery reconnect. Safety outputs require explicit defaults/rearm.
- A consistent declaration is not proof of arbitrary firmware behaviour.
  Review/test the actual BSP and hardware; retain native checks and release gates.

## Carrier and DevKit rules

- For socketed modules follow `docs/engineering/carrier-guidelines.md`.
  Identify the exact purchased board revision and memory/antenna variant;
  verify every socket pad including power, ground, reserved and blocked pins.
- Do not count unavailable memory/USB/boot/onboard-peripheral pins as spare
  GPIO. Review reset/boot states, unpowered I/O and supply backfeed explicitly.
- Check carrier/module top-view orientation, pin 1, pad mapping, socket height,
  antenna keep-out and USB access against manufacturer files and the real board.
- A blank carrier scaffold or passing inventory checker does not validate its
  socket, supply circuit or firmware pin assignment. Never invent a footprint.

## Schematic readability and evidence

- Follow `docs/engineering/schematic-guidelines.md` and its review workflow.
- Before presentation-only edits, capture a `scripts/kit schematic snapshot`.
  Afterward compare against it; separate intentional electrical changes first.
- Inspect every rendered sheet and functional detail, including text, grouping,
  direct local wiring and interface scope. ERC is not a visual review.
- Keep raw renders in ignored `qa/generated/`; keep a factual review summary in
  `qa/design-reviews/` with source/artifact hashes and unresolved findings.
- Never call CLI renders GUI screenshots or mark an unviewed page reviewed.
- `tools/schematic/` owns read-only evidence and hints; it may import only
  `core/` and `kicad/`. It never reserializes or regenerates native files.

## Verification gates

- Schematic ERC and PCB DRC (including schematic parity) must be checked with
  the pinned toolchain, and warnings/exclusions reviewed.
- After final routing, no unintended unconnected connections; compare netlist
  to schematic and identify approved intentional no-connects.
- Confirm connector orientation/pinout, polarity, voltage domains, current,
  fusing/protection, copper/thermal limits, DFM clearances and supply chain.
- For firmware, add module-level plus hardware-interface edge case tests.
- Do not export or label fabrication as GO without signed release checklist and
  physical prototype validation where applicable.

## Commit policy

Only reviewed source and documents to Git. Do not commit locks, `.kicad_prl`,
KiCad backups, temporary QA output or unlicensed vendor assets.

---

# Kit repository rules (PCB-Project-Template itself)

The rules above apply to every generated board project (each project also gets
its own `AGENTS.md`). The rules below apply when working on this kit.

## Git workflow for authorized tasks

- An instruction to implement changes in this repository authorizes agents to
  stage reviewed task-owned source/docs, commit and push the result, unless the
  user explicitly requests local-only work or no commits/pushes. Do not request
  the same authorization again for routine completion of that task.
- Inspect status/diff first. Preserve unrelated or concurrent user changes;
  stage explicit paths only. Never use blanket staging for an unknown tree.
- Run relevant tests and report failures/skips honestly before publishing.
  Missing native validation must remain documented; publishing tooling does
  not approve a hardware design or fabrication release.
- Fetch/check the remote head before publishing. Push only a fast-forward to
  the agreed branch; never force-push, rewrite published history, delete user
  work or discard changes without explicit authorization. If the remote moved,
  inspect and reconcile the changes before retrying.
- Report commit SHA, branch, push outcome and any outstanding validation.
  Do not create a release or tag unless requested.
- This authorizes the agent's task workflow, not automatic Git mutations in
  kit commands. Kit code still never stages, commits or pushes; project
  creation may only `git init` a new project with explicit `--git`.

## Architecture (see docs/ARCHITECTURE.md)

- `tools/` holds all logic as packages by responsibility: `core/` (paths,
  subprocess, parser), `kicad/` (CLI, IPC, design, libraries), `project/`
  (templates, registry, components), `quality/` (verification, firmware),
  `release/` (exports, packaging), `plugins/`, `environment/` (installer),
  `thermal/`, `schematic/` (read-only evidence), `cli/` (entry points). Dependencies point downward to `core/`;
  `cli/` is the only package that depends on everything. Use absolute
  `tools.<package>.<module>` imports.
- `scripts/kit` (`python -m tools`) is the single launcher; `scripts/*.sh`,
  `install_template.command` and `project-manager.command` are thin wrappers.
  The interactive manager (`tools/cli/interactive.py`) and CLI
  (`tools/cli/main.py`) share the same core functions — never duplicate logic.
- `tools/core/kicad_env.py` is the only place that knows machine paths; every
  path can be redirected by an environment variable (tests rely on this).
- `tools/kicad/cli.py` only calls commands/flags discovered from the installed
  CLI's `--help`. `tools/kicad/ipc.py` is stdlib-only; `tools/kicad/ipc_client.py`
  needs `kicad-python` and runs in a bounded subprocess. CLI workflows never need IPC.
- Templates: `meta/templates/` (manifests, KiCad metadata, project-root files),
  `firmware/templates/` (overlays), `hardware/native-defaults/` (KiCad blank files).
- KiCad's official Arduino template is copied from the installed KiCad at
  generation time and never vendored into this repository.

## Changing the kit

- Never write to real user state in tests; use `qa/tests/kit_test_support.py`.
- Do not modify `kicad_common.json` or other KiCad settings while KiCad runs.
- Do not claim a plugin works until `scripts/kit plugins verify NAME` invoked it.
- Do not fabricate circuits, datasheets or 3D models; the `qa/fixtures/divider`
  fixture is a tooling fixture built only from KiCad's official libraries
  (regenerate with `python3 qa/fixtures/build_fixtures.py`).
- Run `python3 test_template.py` (native KiCad tests included when KiCad 10.0.7
  is installed) and keep `docs/IMPLEMENTATION_STATUS.md` and
  `docs/ACCEPTANCE_REPORT.md` factual: report skipped and manual checks separately.
