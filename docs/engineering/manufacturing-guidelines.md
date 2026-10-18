# Manufacturing guidelines

The template assumes no particular fabricator or assembler. Every number in a
profile is an example; your fabricator's published capabilities and stack-ups
are the authority, and they must be checked *before* layout, not after.

## Before layout

- **Capabilities:** minimum track/space, minimum drill and annular ring, via
  types (through only, or blind/buried/micro), hole-to-hole, copper-to-edge,
  solder-mask web and expansion, silkscreen minimum text, board thickness and
  copper weights offered, surface finishes. Enter them as the board's design
  rules (the profiles' `rules` are a starting point).
- **Stack-up:** use the fabricator's documented stack-up for the chosen layer
  count and thickness; required for any impedance-controlled net.
- **Assembly:** whether the assembler needs fiducials, panelization, tooling
  holes, a specific BOM/placement format and side conventions.

## Design for manufacture

- Silkscreen readable after assembly and not on pads; polarity, pin-1 and
  connector orientation marked unambiguously (a mark covered by the part body
  is useless).
- Part orientation: polarized parts in consistent directions where possible.
- Component sourcing: every BOM line has a manufacturer and MPN with stock and
  lifecycle checked; alternates noted (`components/approved-parts`).
- Test points for bring-up and production test.

## Outputs

`scripts/kit export "<project>" --revision <REV>` produces, from the same
verified sources: Gerbers with job file, Excellon drill files with drill map,
BOM (with Manufacturer/MPN columns), placement file (CSV, mm, both sides, DNP
excluded), top/bottom assembly drawings, STEP, schematic PDF, netlist,
optional Interactive HTML BOM, the verification reports and `manifest.json`
(source and artifact SHA-256, KiCad version, gate results, configuration,
known limitations). The export also checks that designators agree between
schematic, board, BOM and placement file.

- Exports are immutable per revision; `scripts/kit releases "<project>"` marks
  any export whose sources or files changed afterwards as **STALE** or
  **MODIFIED**; run it before sending any package so an old one is recognized.
- Manufacturer-specific options (layer naming conventions, panel definitions,
  special drill formats) are not assumed; add them after reading the
  fabricator's requirements and document the change.
- The kit does not upload, quote or order anything.

## Revisions

- Each fabrication of a board is a new revision label (title block `rev`, the
  export `--revision`, the approval file). Never re-use a revision for changed
  data.
- Keep the change list between revisions in `docs/decisions/` or the release
  checklist.

## Engineering questions from the fabricator

Fabricators often return "engineering questions" (EQ) about ambiguous data:
missing stack-up, conflicting drill sizes, silkscreen on pads, unclear outline
layer, plating of slots. Answer them in writing, apply the fix to the *source*
design, re-export as a new revision if anything changed, and record the EQ and
answer with the release.

## Manufacturing-readiness checklist

Use `manufacturing/releases/RELEASE_CHECKLIST.md` for the signed record; this is
the technical content to confirm:

- [ ] Fabricator capabilities and stack-up obtained and entered as design rules
- [ ] `scripts/kit verify "<project>" --release` passes; every exclusion justified in writing
- [ ] Zero unconnected items; schematic parity clean; zones refilled
- [ ] Board outline, holes and cut-outs match the mechanical drawing
- [ ] Connector positions, orientation and pin 1 checked against mating parts
- [ ] Polarity and pin-1 marks visible after assembly
- [ ] All BOM lines have Manufacturer, MPN, approved record; stock and lifecycle checked
- [ ] Footprints and 3D models are the vendor's (or checked against the vendor drawing)
- [ ] Power paths checked for current, voltage, protection and copper (calculations recorded as estimates)
- [ ] Thermal estimate reviewed for dissipating parts; measurement planned at bring-up
- [ ] Export complete, `designator_consistency` COMPLETE, release status CURRENT
- [ ] Gerbers and drill files reviewed in a Gerber viewer (layers, drill alignment, outline)
- [ ] Assembly drawings and placement file reviewed (rotation and side conventions with the assembler)
- [ ] Fabricator engineering questions answered and recorded
- [ ] Approval file signed for this exact revision and Git commit (`scripts/kit export ... --approval ... --authorize`)
