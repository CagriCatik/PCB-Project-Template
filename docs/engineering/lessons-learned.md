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

## Routed-carrier experience (RoverCore)

The following entries generalize reported RoverCore development iterations;
none claims independent prototype measurement. Board-specific dimensions,
voltage settings and component choices are deliberately not template defaults.

### 16. Mounting holes added after routing
+- **Problem:** holes occupy spare space rather than useful chassis supports.
+- **Prevention:** establish [mechanics](mechanical-baseline.md) before placement;
  allow a bounded reroute if the mounting concept changes. Unknown chassis
  dimensions remain provisional. Include washers, tools, cable mates and antenna
  clearance to metal surfaces, not just hole centres.
+- **Evidence:** board-derived dimensioned drawing, 1:1 print with two-axis control
  dimensions and a physical fit check. DRC does not establish chassis suitability.

### 17. Visible sockets mistaken for a populated assembly
+- **Problem:** a model gate passes while the DevKit, OLED or IMU body is absent.
+- **Prevention:** [3D inventory](3d-models.md) separates socket and plugged module,
  real models, drawing-derived geometry, estimated envelopes and bare pads.
+- **Evidence:** isolated and assembled views plus independent STEP inclusion
  review. A CAD listing/file existence is not a successful body download/render.

### 18. Cleanup and import scripts damage routed copper
+- **Problem:** area deletion removes unrelated nets; a sync resets manual layout;
  blanket via cleanup removes real ground/power connections.
+- **Prevention:** separate sync/bootstrap, recoverable copies, connectivity-owned
  edits and native before/after object comparison. Refill before DRC and inspect
  power-pour islands/neck widths. Do not treat via counts as proof of restoration.
+- **Evidence:** intended change regions, copper/return review and native checks.
  A crash after saving requires reopening and validation, not hiding the exit code.
- **Automated:** `scripts/kit board diff BEFORE AFTER --region ...` lists every added/removed track,
  arc and via, moved footprints and changed zones, flags changes outside the intended regions and
  short import slivers. It does not judge electrical correctness; refill and DRC still follow.

### 19. DNP parts merged with populated parts in the BOM
+- **Problem:** matching part values are grouped despite different assembly state.
+- **Implemented:** export groups include `${DNP}`; consistency checks compare each
  row member's DNP state with the schematic. Regression covers correct reference
  sets with an incorrect DNP grouping; native export still requires KiCad 10.0.7.

### 20. Combined drill files obscure plating intent
+- **Implemented:** explicit separate PTH/NPTH CLI export and filename-policy check.
  Empty sets may be absent. Obsolete combined files must not accompany the sets.
+- **Manual:** compare drill geometry, diameters and slots to the board and the
  fabricator preview. Parser precision must come from format/units; never loosen
  tolerance to hide premature rounding. Filename checks are not geometry checks.
- **Automated:** `scripts/kit fab check PROJECT PACKAGE` compares every drill hit with every
  board hole per plating (tolerance = half the last decimal place of the files), plus positions
  and the job layer count. It does not inspect Gerber copper or replace the fabricator preview.

### 21. DC estimates mistaken for thermal guarantees
+- **Prevention:** retain layer thickness/plating provenance, boundary conditions
  and grid sensitivity. Shared vias carry unequal current; thermal spokes and
  zone necks may dominate. Test-condition copper area is not automatically a
  layout requirement. See [routing-guidelines.md](routing-guidelines.md).
+- **Evidence:** comparable DC model cases and separately planned temperature,
  transient and physical prototype measurements.

### 22. Publishing mistaken for hardware approval
+- **Prevention:** README/Pages views share the current source revision. A push is
  source publication; DRAFT/NO-GO stays independent of Git status. Existing
  source-hash/release-status mechanisms identify obsolete fabrication packages.
+- **Firmware:** host state-machine tests do not validate target polling gaps,
  watchdog wiring, ADC calibration or real actuator behaviour. Start firmware
  independently of the mechanical fit check; document each evidence boundary.
