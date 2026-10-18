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

## Before changing native KiCad files

- Confirm KiCad {{KICAD_VERSION}}; refuse scripted writes while `~*.lck` lock files exist.
- Use the real KiCad CLI/APIs; never fabricate reports or claim IPC is available when it is not.
- Make small, auditable changes and re-run `scripts/kit verify`.
- Never substitute dummy 3D models or invented datasheets for real vendor data.
- Label every calculation as an estimate; estimates do not replace measurement.

## Verification and release

- ERC, DRC and schematic parity run with the pinned toolchain; review warnings and exclusions.
- After routing there must be no unintended unconnected items.
- Confirm connector orientation/pinout, polarity, voltage domains, current, protection,
  copper/thermal limits, DFM clearances and supply chain.
- Firmware changes need module-level and hardware-interface edge-case tests.
- A GO release needs a signed approval (`manufacturing/approval.example.json`), a clean Git
  commit, passing release-mode verification, and explicit `--authorize`.

## Git ownership

Only the project owner stages, commits and pushes. Agents must not run `git add`,
`commit`, `push`, `merge`, `rebase`, `reset`, `clean`, `stash`, `tag`, `cherry-pick`
or working-tree-changing `checkout`/`switch`. Never commit locks, `.kicad_prl`,
backups, generated QA output or unlicensed vendor assets.
