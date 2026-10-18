# Local KiCad libraries

Prefer official KiCad libraries for standard parts. If needed, create
`symbols/ProjectSymbols.kicad_sym` through KiCad's Symbol Library Manager and
`footprints/ProjectFootprints.pretty/` through the Footprint Library Manager.
Save root `sym-lib-table` and `fp-lib-table` to Git; use project-relative paths:

- Symbol: `${KIPRJMOD}/hardware/libraries/symbols/ProjectSymbols.kicad_sym`
- Footprint: `${KIPRJMOD}/hardware/libraries/footprints/ProjectFootprints.pretty`
- 3D: `${KIPRJMOD}/hardware/libraries/3d-models/<vendor-file>.step`

Do not create placeholder library tables that reference non-existent files.
