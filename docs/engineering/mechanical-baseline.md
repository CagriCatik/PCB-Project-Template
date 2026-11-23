# Mechanical baseline before routing

These practices come from the RoverCore iteration: holes added after routing
fit the remaining space, but did not make a useful mounting pattern. Fixing
that later required a larger outline and local rerouting. The dimensions of
that board are not template defaults.

## Decide before placement

Record the following in `hardware/mechanical/` and link the decision from the
placement review:

| Item | Record and review |
| --- | --- |
| Reference system | Board-local datum, units, top/bottom view and axis directions |
| Outline | Available chassis/enclosure area, board thickness and tolerances |
| Mounting | Actual NPTH/PTH footprints, screw, washer, standoff and tool envelopes on both sides |
| External access | Mating plugs, latch travel, cable exit/bend, fingers, buttons and USB plugs |
| Modules | Exact revision, socket height, protruding pins and component envelopes |
| RF | Manufacturer antenna region and clearance to the nearest metal surface, including hardware/chassis |
| Status | Confirmed versus provisional constraints, source and pending physical fit checks |

No enclosure drawing available means **provisional**, not "mechanics passed".
An early placement/routing study may proceed with this limitation explicitly
recorded. Do not run another search for holes merely to avoid changing copper.
Choose the mounting concept first; permit local replacement/rerouting when
the mechanically useful positions require it. Four corner holes are an option,
not a rule overriding the chassis or antenna requirements.

Real mounting footprints must be present in both the schematic and board,
with intentional BOM/position exclusions. Comment circles are not drill hits.
Lock agreed positions; implement copper keep-outs on the required layers.
Use dimensions from the chosen hardware, not a universal clearance radius.

## Review the populated assembly

Check with and without plug-in modules, top and bottom, plus detail views of
buttons, USB and mounting hardware. Distance to a hole centre does not establish
clearance to a washer, tool or screw. Estimated module heights cannot establish
collision clearance. A socket model does not represent the module above it.
See [3d-models.md](3d-models.md).

An insulating support may be appropriate for a module insertion load. Check
bottom-side parts, solder tails, antenna clearance and rubbing; solder mask
alone is not mechanical abrasion protection. Match actual mounting height and
avoid unintended board preload. Confirm deflection on the physical assembly.

## Board is the geometry source

Read outline and hole locations from the current board for drawings and renders;
do not duplicate coordinates in multiple scripts. Use a board-local datum so a
pure translation in the editor does not invalidate placement tools. Abort if
the supposed translation also contains rotation or geometry changes.

For physical fit, produce a 1:1 print with horizontal and vertical control
dimensions. Print at actual size, measure both controls and test real mating
parts. Clearly label provisional geometry and the source revision/hash.

## Mechanical changes after routing

1. Work on a recoverable copy; preserve the owner's current edits.
2. Move only the intended parts and their owned copper. Remove connections by
   connectivity to a pad/via/branch, not an unrestricted rectangular deletion.
3. Compare tracks, vias, zones and footprints before/after, with declared change
   regions. Counts alone do not prove restoration. Never delete every via that
   appears unused to a custom script; refill and inspect native DRC findings.
4. Refill zones, run native DRC/parity and review filled copper and return paths.
   A new signal can cut a power pour into islands while still looking connected.
5. Recalculate affected supply paths with identical loads, stackup, temperature
   and boundary conditions. Record voltage drop and bottlenecks as estimates.
6. Refresh drawings, model views and a new DRAFT export together. Old packages
   remain immutable and become stale; do not reuse them because DRC still passes.

These are review obligations, not an implemented automatic mechanical approval
gate. Finish the bounded task; repeat review only for new changes or findings.
