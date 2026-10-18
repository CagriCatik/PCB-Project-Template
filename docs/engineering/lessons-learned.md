# Lessons learned (engineering)

Recurring failure modes in PCB projects and how this template addresses them.
(Lessons about the *kit's* own implementation are in the kit's
`docs/LESSONS_LEARNED.md`.)

**Sources.** Scenarios 1–14 are the ones named in the template-hardening brief
as observed in a complete four-layer ESP32 PCB development tutorial. The
tutorial itself was not available while this file was written, so the
"problem observed" entries describe each failure mode generally rather than
quoting the tutorial; nothing tutorial-specific is invented. Entries marked
**additional** are further recommendations, not tutorial observations.

Each lesson: problem · cause · principle · prevention · automated check ·
manual review · impact.

### 1. Broken footprint references
- **Problem:** after reorganizing folders, footprints or symbols fail to load or silently become placeholders.
- **Cause:** library tables or footprint paths pointed to machine- or folder-specific locations.
- **Principle:** project libraries live inside the project and are referenced via `${KIPRJMOD}`.
- **Prevention:** keep custom libraries in `hardware/libraries/`; register with `scripts/kit libraries register`.
- **Automated:** `library_references`, `portability` gates; relocation test with `qa/fixtures/custom-lib`.
- **Manual:** after adding a third-party library, open the project from a different path once.
- **Impact:** prevents boards that cannot be opened or exported on another machine.

### 2. Datasheet requirements missed during schematic design
- **Problem:** required external parts, strapping pins or sequencing omitted.
- **Cause:** schematic drawn from memory or an example instead of the datasheet.
- **Principle:** every design decision traces to a datasheet page, a calculation, an application note or a written assumption.
- **Prevention:** [datasheet-review.md](datasheet-review.md) checklist per part before placement.
- **Automated:** `component_metadata` (Datasheet/MPN fields present), `bom` (approved record).
- **Manual:** checklist review with page references.
- **Impact:** avoids non-booting or unreliable first prototypes.

### 3. Incorrect or incomplete decoupling
- **Problem:** missing, wrong-value or badly placed decoupling; derated ceramic values.
- **Cause:** generic "100 nF per pin" habit, nominal capacitance assumed.
- **Principle:** follow the device's decoupling recommendation; account for DC-bias derating; minimize loop area.
- **Prevention:** decoupling drawn per supply pin in the schematic; placed first in each group.
- **Automated:** none can judge adequacy (ERC/DRC only check connectivity).
- **Manual:** schematic and placement review against the datasheet.
- **Impact:** supply noise, resets, radio and ADC problems.

### 4. Placement without routing consideration
- **Problem:** a placement that forces long detours, plane splits or vias in critical paths.
- **Cause:** placing for neatness, then routing.
- **Principle:** placement serves current loops, return paths and routing channels.
- **Prevention:** [placement-guidelines.md](placement-guidelines.md); compare alternatives before routing.
- **Automated:** DRC unconnected items only after routing; `thermal` estimate for heat.
- **Manual:** routability and return-path review before routing starts.
- **Impact:** fewer re-layouts, better EMC.

### 5. Invalid assumptions about signal length matching
- **Problem:** time spent meandering SPI/I²C/GPIO traces while real constraints were ignored.
- **Cause:** treating length matching as general good practice.
- **Principle:** match lengths only where a specification gives a timing budget; within differential pairs as specified.
- **Prevention:** [routing-guidelines.md](routing-guidelines.md) marks constraints vs heuristics.
- **Automated:** none (requirements are interface-specific).
- **Manual:** routing review against interface specifications.
- **Impact:** simpler routing, less coupling.

### 6. Inappropriate copper zone assignments
- **Problem:** zones on the wrong net, isolated islands, planes split under fast signals.
- **Cause:** zones created early and not reviewed after changes; zones not refilled.
- **Principle:** each zone has a purpose and a net; reference planes stay continuous.
- **Prevention:** refill zones before checks; review zone nets per layer.
- **Automated:** DRC (unconnected, isolated copper per configured severities); thermal estimate warns about unfilled zones.
- **Manual:** layer-by-layer review of planes and splits.
- **Impact:** avoids shorts, opens and EMC failures.

### 7. Insufficient power-path verification
- **Problem:** traces, vias or connectors too small for the current; regulators overheating; missing protection.
- **Cause:** power tree not written down; current and dissipation not calculated.
- **Principle:** document each rail's source, maximum load, protection and copper; calculate and mark as estimate; measure.
- **Prevention:** `hardware/interfaces/power_budget.csv`; net classes for power.
- **Automated:** `thermal` gate (estimate, opt-in); DRC enforces net-class widths you set.
- **Manual:** power-tree review, bring-up current measurements.
- **Impact:** prevents burnt traces and brown-outs.

### 8. Unjustified ERC/DRC exclusions
- **Problem:** real errors hidden by exclusions or lowered severities.
- **Cause:** making checks pass instead of fixing causes.
- **Principle:** an exclusion needs a written reason and reviewer.
- **Prevention:** the kit lists every excluded violation separately in reports; it never edits KiCad rules to pass.
- **Automated:** `erc` / `drc` gate reports show `excluded` findings.
- **Manual:** review each exclusion at every release.
- **Impact:** keeps checks meaningful.

### 9. Missing or misaligned 3D models
- **Problem:** collisions or wrong heights discovered at assembly; models missing after library moves.
- **Cause:** unresolved model paths, legacy variables, generic substitutes.
- **Principle:** use the vendor's model or check it against the vendor drawing; report missing models, never fake them.
- **Prevention:** `${KICAD10_3DMODEL_DIR}` or `${KIPRJMOD}` paths.
- **Automated:** `models_3d` gate (missing/unresolved), `portability` (legacy/absolute paths).
- **Manual:** 3D view alignment check of every new footprint.
- **Impact:** mechanical fit on the first build.

### 10. Stale BOM references
- **Problem:** BOM from an older schematic sent with newer Gerbers.
- **Cause:** outputs generated at different times and copied by hand.
- **Principle:** all outputs from one verified source state, with hashes.
- **Prevention:** `scripts/kit export` produces everything at once; `scripts/kit releases` flags STALE/MODIFIED packages.
- **Automated:** `designator_consistency`, source hashes in the manifest.
- **Manual:** release review confirms status CURRENT.
- **Impact:** assembler builds what was designed.

### 11. Ambiguous assembly orientation
- **Problem:** diodes, ICs or connectors assembled rotated.
- **Cause:** pin-1/polarity marks hidden under the body or missing; rotation conventions differ between tools.
- **Principle:** marks visible after assembly; confirm rotation conventions with the assembler.
- **Prevention:** assembly drawings in every export; [manufacturing-guidelines.md](manufacturing-guidelines.md).
- **Automated:** none (visual property).
- **Manual:** assembly drawing and placement-file review.
- **Impact:** fewer assembly defects.

### 12. Manufacturing-file inconsistencies
- **Problem:** drill files not matching copper, missing outline layer, BOM/placement designators disagreeing.
- **Cause:** separate manual exports with different settings.
- **Principle:** one scripted export with recorded commands and checks.
- **Prevention:** `scripts/kit export`; reproducibility check (`compare-exports`).
- **Automated:** designator consistency, normalized digests, export completeness.
- **Manual:** Gerber viewer review.
- **Impact:** fabricator accepts the data without rework.

### 13. Manufacturer engineering questions
- **Problem:** production delayed by questions about stack-up, drills, mask or outline.
- **Cause:** fabrication intent not fully stated in the data.
- **Principle:** state stack-up, finishes and special requirements explicitly; answer EQs in the source.
- **Prevention:** capability check before layout; fabrication notes.
- **Automated:** none.
- **Manual:** record each EQ and its answer with the release.
- **Impact:** shorter lead times, fewer surprises.

### 14. Treating DRC success as proof of correct hardware
- **Problem:** a board passing all checks does not work.
- **Cause:** checks only verify rules and consistency, not function.
- **Principle:** checks are prerequisites for review; function is proven by review, calculation and measurement.
- **Prevention:** drafts are always NO-GO; GO needs a signed approval whose `prototype_validation` gate is PASS (or NOT_APPLICABLE) with an evidence file.
- **Automated:** release gate refuses GO without approval evidence.
- **Manual:** design review, bring-up plan (`docs/bringup.md`).
- **Impact:** honest release decisions.

### 15. Untested toolchain versions (additional)
- **Problem:** a different KiCad version silently changes outputs or rule behaviour.
- **Principle:** pin the tool version; make deviations visible.
- **Automated:** exact-version check; `KICAD_KIT_ALLOW_UNTESTED=1` marks reports UNTESTED and blocks GO releases.
- **Impact:** reproducible manufacturing data.
