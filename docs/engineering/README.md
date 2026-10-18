# PCB engineering guidelines

Practical rules for designing a board with this template. They are copied into
every generated project (`docs/engineering/`), so the project carries its own
reference. Commands assume the kit checkout; `<project>` is your project path.

**Rule of precedence used throughout:** manufacturer datasheets and application
notes, then your own documented calculations, then fabricator capabilities, then
the general heuristics written here. A heuristic never overrides a datasheet.

## Design workflow

| Step | What you do | Guideline | Evidence the kit can produce |
| --- | --- | --- | --- |
| 1. Requirements | Write measurable requirements (voltages, currents, interfaces, environment, size) | `docs/requirements.md` | — |
| 2. Component selection | Choose real manufacturer parts against the requirements | [component-selection.md](component-selection.md) | `scripts/kit components add/validate` |
| 3. Datasheet review | Extract every constraint the part imposes | [datasheet-review.md](datasheet-review.md) | Record in `components/approved-parts/*.json` |
| 4. Schematic | Capture function and interfaces readably | [schematic-guidelines.md](schematic-guidelines.md) | `scripts/kit verify` (ERC, library, pin/pad, metadata gates) |
| 5. Board setup | Choose a profile, confirm stack-up and rules with the fabricator | [manufacturing-guidelines.md](manufacturing-guidelines.md) | `scripts/kit templates profiles` |
| 6. Placement | Place by mechanics, function and current paths before routing | [placement-guidelines.md](placement-guidelines.md) | `scripts/kit thermal analyze` (estimate) |
| 7. Routing | Route by return paths and real constraints | [routing-guidelines.md](routing-guidelines.md) | DRC, parity, unconnected items |
| 8. Verification | Run the gates, review every finding and exclusion | `docs/verification-plan.md` | `scripts/kit verify --release` |
| 9. Manufacturing | Export, review, approve, release | [manufacturing-guidelines.md](manufacturing-guidelines.md) | `scripts/kit export`, `scripts/kit releases` |
| 10. Bring-up | Power up safely, measure, compare with requirements | `docs/bringup.md` | — |

Recurring mistakes and how this template guards against them:
[lessons-learned.md](lessons-learned.md).

## What automation cannot tell you

ERC, DRC, parity and the kit's gates check *consistency* and *rules you have
entered*. They cannot know whether the circuit does what you intended, whether
a regulator is stable, whether a trace carries its current without overheating
or whether a connector is mirrored relative to its mate. A clean report is a
prerequisite for review, never a substitute for it.
