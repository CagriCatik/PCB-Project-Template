# Thermal model inputs

Used by `scripts/kit thermal analyze "<project>"` and the optional `thermal`
verification gate (see `docs/THERMAL_ANALYSIS.md` in the kit).

- `power_sources.csv` – one row per dissipating component:
  `reference` (as on the board), `power_w` (steady-state loss), `basis`
  (`calculation`, `datasheet`, `measurement` or `estimate`), optional
  `theta_jb_c_per_w` (junction-to-board from the datasheet) and `limit_c`
  (temperature limit to check), `notes` (where the number comes from).
  KiCad does not know real losses; derive them from the circuit, operating
  profile and datasheets. The file starts empty on purpose.
- `thermal.json` – ambient, grid, convection coefficients, materials, limits.

Results are estimates from a simplified model and must be confirmed by
measurement on a prototype.
