# 3D model provenance and assembly coverage

A footprint path, a CAD search result and a rendered component are three
different things. `models_3d` checks visible model assignments and resolved file
existence only. It does not inspect dimensions, licensing, module completeness
or the bodies included in the board STEP export.

## Record each physical position

Maintain a model inventory under `hardware/libraries/` when doing a populated
assembly review. Record reference, exact MPN/package/revision, model path,
origin (manufacturer / library / community / drawing-derived / review envelope /
intentionally bodyless), source URL, file hash, licensing/redistribution status,
drawing revision and checked dimensions, rotation/offset, estimated dimensions,
and render/STEP inclusion status. This is a review record, not a schema currently
validated by a kit command.

Distinguish bare test pads/net ties and deliberately unpopulated parts from
missing physical components. For socketed boards record the socket and plugged
module separately: two socket bodies cannot establish a populated DevKit view.

## Find and check models

1. Search exact manufacturer part number and package variant. A cable XT plug
   is not the corresponding right-angle PCB plug. A similar transistor part
   number is usable only after confirming the same package geometry.
2. Open the actual download: some "CAD available" listings offer only symbols
   and footprints. Report account requirements, denied requests and absent
   formats separately; a failed request does not prove no model exists.
3. Prefer manufacturer data, but accept a properly licensed library/community
   model checked against the manufacturer drawing. Do not pause independent
   parts because one portal needs an account or terms acceptance. Do not submit
   personal details or accept new terms without the user's authorization.
4. A model constructed from a drawing is permitted if labelled **drawing-derived**,
   with source dimensions and assumptions. It is not a manufacturer model or a
   measurement. Review envelopes must remain distinct and cannot prove fit.
5. Store redistributable files project-locally using `${KIPRJMOD}` and retain
   required license notices. For local-only vendor files record retrieval steps,
   checksum and expected destination; warn that a clean clone lacks that body.

## Placement and views

Change model transforms only; preserve footprint/pad positions, nets and routing.
Check top/front/side/isometric views for pin 1, polarity, pins and locating pegs,
body/terminal dimensions, seating height and mating direction. Compare to the
manufacturer drawing as well as to the footprint: matching two incorrect
representations is not independent validation. For custom geometry inspect face
orientation and closed solids; a mirrored mesh may look hollow.

Render an isolated detail and the populated board, with and without modules.
When rendering a copy elsewhere, resolve `${KIPRJMOD}` against the original
project or copy the local assets; do not commit absolute machine paths back to
the design. Captions must distinguish verified models, estimated envelopes and
missing bodies. README/Pages must not silently replace a complete review view
with a native render that omits those components.

Check the **exported STEP assembly separately**. A mesh visible in the KiCad
viewer may be absent from STEP. State this limitation before enclosure CAD or
collision review; a successful STEP command and file existence are insufficient.
An entity-count comparison is not geometric equivalence. No kit check here
certifies that a 3D body represents the purchased part.
