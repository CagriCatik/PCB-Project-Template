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

## Git ownership — hard restriction

The repository owner alone stages, commits and pushes. Agents must never run
`git add`, `commit`, `push`, `merge`, `rebase`, `reset`, `clean`, `stash`, `tag`,
`cherry-pick`, or a `checkout`/`switch` that changes the working tree; must not
create branches, pull requests or releases; and must not ask other services or
agents to do so. Allowed: `git status`, `diff`, `log`, `ls-files`, `remote -v`,
`branch --show-current`, `rev-parse`. No kit code may commit or push; project
creation may only `git init` a *new* project on explicit `--git`. Leave all
changes unstaged and report them.

## Architecture (see docs/ARCHITECTURE.md)

- `tools/` holds all logic as packages by responsibility: `core/` (paths,
  subprocess, parser), `kicad/` (CLI, IPC, design, libraries), `project/`
  (templates, registry, components), `quality/` (verification, firmware),
  `release/` (exports, packaging), `plugins/`, `environment/` (installer),
  `thermal/`, `cli/` (entry points). Dependencies point downward to `core/`;
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
