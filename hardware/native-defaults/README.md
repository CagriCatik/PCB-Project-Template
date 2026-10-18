# Native blank defaults

`default.kicad_pro`, `default.kicad_sch` and `default.kicad_pcb` were generated
by KiCad Manager 10.0.7 from its built-in Default template, with no design edits.
The Generic PCB and STM32 Embedded templates copy them, rename them to the
project name and give the schematic a fresh root-sheet UUID (a stable UUID for
templates installed into KiCad's template directory).

They contain no circuit and no board outline, so a new blank project fails DRC
with `invalid_outline` until an outline is drawn. That failure is expected.
