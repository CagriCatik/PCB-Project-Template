# Schematic review workflow

Use this workflow for functional structure, grouping, wiring, labels and
comments. It complements the electrical gates; it is not an automatic layout
optimizer or a release gate. Run commands from the **kit checkout**; generated
board repositories do not carry a second copy of the tools.

## 1. Establish the electrical baseline

Close/save KiCad first so the disk represents the intended design. Snapshot the
root sheet, not each child independently:

```sh
scripts/kit schematic snapshot /path/to/Board.kicad_sch \
  --output /path/to/project/qa/generated/before.json
```

A snapshot contains KiCad's XML netlist plus the native hierarchy, component
fields/flags, interfaces, symbol/pin identities, embedded library digest and
source hashes. Repeated sheets and multi-unit components are retained. Native
coordinates, rotations and text placement are excluded from the semantic
comparison. Auto-generated net names and net codes are excluded, but their pin
membership is compared; explicitly named nets are compared with their names.

Snapshots require a new destination and never overwrite an earlier baseline.
Use the same KiCad version for both sides. Baselines are generated artifacts:
retain/copy them with review evidence as needed, but do not commit raw runs.
For an old revision use a separate owner-prepared copy, without switching the
active editor's working tree. The tool itself makes no Git mutations.

## 2. Review and improve the drawing

Follow [schematic-guidelines.md](schematic-guidelines.md). Inspect each sheet:

- One clear purpose and numbered functional groups; short headings describe
  function, not just the IC name. Avoid arbitrary symbol grids and giant pages.
- Power/signal flow reads left to right; local paths are direct wires. Do not
  replace a short wire with two labels just because placement is difficult.
- Decoupling, feedback, compensation and protection sit near their functional
  circuit. Show Kelvin connections and layout constraints where relevant.
- Comments explain intent, voltage/current domains, default states, thresholds
  and assumptions. Separate calculations, candidates and measured facts.
- Reference/value text stays clear of bodies, wires, labels, group boundaries
  and title blocks. Check rotated/mirrored symbols and multiline comments.
- Hierarchical pins express functional interfaces with direction. Review global
  labels explicitly; any deliberate exception has a reason in the summary.
- Connector view, pin 1, polarity and mating-side orientation are unambiguous.

Finish electrical corrections first and create a fresh baseline. A purely
visual refactor must compare equal electrically afterward. A detected change
requires investigation; do not suppress it or re-baseline merely to get green.

## 3. Render every sheet and detail

```sh
scripts/kit schematic review /path/to/Board.kicad_sch \
  --baseline /path/to/project/qa/generated/before.json \
  --views /path/to/project/qa/schematic-views.json
```

The command requires KiCad **10.0.7** and Poppler's `pdftoppm` on PATH
(`brew install poppler`, or `apt install poppler-utils`). No Python image
package is required. It creates a unique directory under the project's
`qa/generated/schematic-review/` containing:

- Root PDF with all sheet instances, numbered PNG overviews at 150 dpi;
- configured functional detail PNGs at 300 dpi;
- current snapshot, ERC JSON, an HTML image index and manifest;
- source/artifact SHA-256 hashes, command records, KiCad version and Poppler
  version output, comparison differences and conservative layout hints.

Pass `--dpi 300` for higher-resolution overviews; `--output DIRECTORY` changes
the parent of the unique run directory. It never reuses an older render.
Failed exports/rasterization, changed sources and invalid crops fail the run;
the manifest records `FAILED`, never a fresh passing image index.

Create `qa/schematic-views.json` from `schematic-views.example.json`. Views use
**PDF page number** (1-based) and `[x, y, width, height]` in millimetres from the
paper's top left. Each id becomes `detail-ID.png`. Keep the same config for
before/after crops and review page ordering if hierarchy changes. Overviews
are generated for every page even with an empty view list; populate detail
views for each functional group before completing the review. Crops outside
the rendered page are rejected.

These are **CLI renders**, not screenshots from the KiCad window. If actual
GUI screenshots are requested, capture them separately into the ignored run
folder and identify their origin in the review. Do not relabel renders.

## 4. Compare and record actual inspection

```sh
scripts/kit schematic compare /path/to/project/qa/generated/before.json \
  /path/to/project/qa/generated/schematic-review/review-RUN/snapshot.json
scripts/kit schematic lint /path/to/Board.kicad_sch
```

`compare` exits 20 on differences, unsupported toolchains or a toolchain mismatch;
0 requires equality and supported 10.0.7 evidence.
`review` exits 20 for active ERC findings or semantic/toolchain differences;
0 means evidence generation completed without those findings. **It never means
visual or electrical approval.** `lint` emits advisory hints only. It checks
visible text anchors that coincide or fall outside standard A-series paper,
and sheets lacking text annotations. It cannot judge full text bounds, symbol
bodies, pin names, mirrored text or custom title-block clearances.

Open `index.html` and inspect every overview and crop at readable zoom. Never
mark an unviewed sheet reviewed. Use the versioned template
`qa/design-reviews/schematic-review-template.md` for findings and closure.
Record the source/artifact hashes, tool versions, inspected images, reviewer,
known limitations and explicit verdict. Raw runs remain ignored; the summary
is source. `visual_status` in the automatic manifest deliberately remains
`NOT_REVIEWED`—no automated hint or unchanged ERC count can approve it.

## Check retained evidence before using it

```sh
scripts/kit schematic status /path/to/project/qa/generated/schematic-review/review-RUN/manifest.json
```

This checks recorded artifact hashes and current schematic/project hashes.
It returns `CURRENT`, `STALE` (sources changed), `MODIFIED` (artifacts changed)
or `INCOMPLETE`; evidence from another toolchain is `UNSUPPORTED`. Only `CURRENT` exits 0; actual visual approval is still separate.
Archived runs moved away from their recorded source path become stale.

## Boundaries

- Snapshot equality is a scoped consistency check, not circuit correctness.
  In particular no-connect **counts**, not their intended pin associations,
  are inventoried; review no-connect intent and ERC separately. Native UUID
  changes are treated as differences even if connectivity is unchanged.
- Embedded library changes are deliberately detected, including default
  presentation changes: review these explicitly instead of ignoring them.
- The snapshot binds schematic files, matching project settings and the local
  symbol-library table when present. External/global libraries, fonts, user
  settings and custom drawing sheets are not fully hashed. Keep the toolchain
  and environment consistent; manifests do not guarantee pixel equality.
- Native render integration must be checked on KiCad 10.0.7. Snapshots and review runs reject
  untested versions even when the general diagnostic override is set.
- No automatic schematic writer, wire router or generic regex editor is added.
  KiCad files remain authoritative. Any future generator must be opt-in,
  refuse live editor/lock states and prove connectivity preservation separately.
