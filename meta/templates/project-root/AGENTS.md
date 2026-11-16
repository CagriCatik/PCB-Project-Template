# Rules for Codex / Claude / other agents ({{PROJECT_NAME}})

Created from the {{TEMPLATE_TITLE}} template of PCB-Project-Template {{KIT_VERSION}}.

## Architecture invariants

1. One KiCad {{KICAD_VERSION}} project; `.kicad_pro`, `.kicad_sch`, `.kicad_pcb` at the root.
2. Hardware truth lives in the schematic, board and verified part datasheets;
   `hardware/interfaces/pinmap.csv` is a reviewed interface artifact, not a second truth.
3. Keep firmware HAL/BSP (`firmware/bsp`) separate from application logic (`firmware/app`).
4. Custom KiCad libraries are local under `hardware/libraries` and referenced via `${KIPRJMOD}`.
5. Generated outputs are not source. Never hand-edit Gerbers, drill, position files,
   PDFs or ERC/DRC reports.

## Mandatory toolchain

- KiCad **{{KICAD_VERSION}}** is required for native design edits, ERC/DRC,
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

- Confirm KiCad {{KICAD_VERSION}}; refuse scripted writes while `~*.lck` lock files exist.
- Use the real KiCad CLI/APIs; never fabricate reports or claim IPC is available when it is not.
- Make small, auditable changes and re-run `scripts/kit verify`.
- Never substitute dummy 3D models or invented datasheets for real vendor data.
- Label every calculation as an estimate; estimates do not replace measurement.

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

## Schematic review

- Use `docs/engineering/schematic-guidelines.md` and `schematic-review.md`.
- Capture a baseline snapshot before presentation-only edits; compare after edits.
  Do electrical changes separately and list their intended net/part differences.
- Render and inspect every sheet plus functional detail crops. Keep source-bound
  evidence in ignored `qa/generated/`, a factual summary in `qa/design-reviews/`.
- No overlapping labels/fields, hidden functional paths or undocumented label
  islands. Use direct local wires, functional groups and short intent comments.
- Never infer visual approval from ERC, unchanged counts or automated hints.
  Record actual inspection and any unresolved layout issues explicitly.
- CLI exports are renders, not GUI screenshots. If screenshots are requested,
  capture the actual KiCad window as additional evidence; do not substitute.

## Verification and release

- ERC, DRC and schematic parity run with the pinned toolchain; review warnings and exclusions.
- After routing there must be no unintended unconnected items.
- Confirm connector orientation/pinout, polarity, voltage domains, current, protection,
  copper/thermal limits, DFM clearances and supply chain.
- Firmware changes need module-level and hardware-interface edge-case tests.
- A GO release needs a signed approval (`manufacturing/approval.example.json`), a clean Git
  commit, passing release-mode verification, and explicit `--authorize`.

## Git workflow for authorized tasks

- Repository implementation tasks authorize the agent to stage reviewed,
  task-owned source/docs, commit and push unless the user requests local-only
  work or forbids commits/pushes. No repeated confirmation is needed.
- Inspect status/diff; preserve unrelated user changes and stage explicit paths.
  Run relevant checks, disclose failures/skips and keep hardware release
  approval separate from publishing source changes.
- Check/fetch the remote head before publishing; use a plain fast-forward to
  the agreed branch. No force-push, history rewrite, deletion or discarding
  user work without explicit authorization. Inspect/reconcile concurrent
  remote changes before retrying.
- Report commit SHA, branch, push result and outstanding verification. Tags
  and releases need their own request.
- Never commit locks, `.kicad_prl`, backups, generated QA output or unlicensed
  vendor assets. Kit commands themselves do not stage, commit or push.
