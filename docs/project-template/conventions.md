# Project conventions

One root native project per board. Keep the project, schematic and PCB basenames
identical. Use the existing hardware/firmware/components/manufacturing/docs/qa
boundaries. Tooling lives in the PCB-Project-Template kit, not in the project;
run it with `scripts/kit <command> "<project>"` from the kit checkout.

Record design revision in KiCad's title block and release approval; use the same
identifier in export `--revision`. Review requirement IDs, schematic nets and
firmware mapping together. Do not derive board connectivity from the pinmap CSV.

Project-local symbols and footprints use `${KIPRJMOD}`. Real manufacturer models
need provenance and redistribution rights. Keep optional MCU SDK source separate
from platform-independent application code. Generated build/report directories
contain no authored source.

Git is optional at creation (`--git`) and mandatory for reviewed GO releases.
Review changes before staging or committing. The kit initializes repositories
only on explicit `--git`, never commits, pushes, rewrites history or stages files.
Ignore local state and generated outputs; archive reviewed release snapshots with
the exact source commit and manifest. See the directory guide in `README.md`.

Project creation does not auto-open editors. Use `scripts/kit open "<project>"` explicitly.
No automation writes into an open native design; lock detection blocks it.
