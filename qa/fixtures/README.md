# Reference projects

Small, genuine KiCad 10.0.7 projects used to exercise the kit with real KiCad
tools. They are **tooling references, not reviewed circuits**: no electrical,
thermal or manufacturing suitability is claimed. Regenerate both with
`python3 qa/fixtures/build_fixtures.py` (KiCad 10.0.7 required).

| Project | Purpose | Content | Validation status (automated, KiCad 10.0.7) |
| --- | --- | --- | --- |
| `divider/` | Minimal two-layer PCB; manufacturing-export example | J1 3-pin header, R1/R2 0805 from KiCad's official libraries via the global tables; routed on F.Cu; 23 × 17 mm outline | ERC 0, DRC 0, unconnected 0, parity 0; portability, library, pin/pad and 3D-model gates pass; all ten export outputs complete and reproducible; IBOM, Freerouting and KiKit run on it. Metadata/BOM gates fail by design (no MPNs: it is not a real product). |
| `custom-lib/` | Portable project-local library example | TP1/TP2 from `Project_Symbols` / `Project_Footprints` libraries inside the project (`${KIPRJMOD}` tables, copied from KiCad's official libraries with attribution in `hardware/libraries/ATTRIBUTION.md`), R1 from the official library | ERC 0, DRC 0, parity 0; library, portability and pin/pad gates pass before and after the project is moved to a path with spaces and non-ASCII characters. `models_3d` reports TP1/TP2: KiCad's test-point footprint has no 3D model, and none is invented. |

A four-layer reference board is not included: there is no circuit in this kit
that needs four layers, and an artificial one would only look complex. The
four-layer *starting point* is the `4-layer` profile (`scripts/kit templates
profiles`), whose stack-up, rules and net classes are read back by pcbnew in the
tests.

## Manufacturing-export example

```sh
cp -R qa/fixtures/divider "/tmp/divider example"
scripts/kit verify  "/tmp/divider example"
scripts/kit export  "/tmp/divider example" --revision A1
scripts/kit releases "/tmp/divider example"         # CURRENT until a source changes
```

Exports are written under the copied project, never into `qa/fixtures/`.
