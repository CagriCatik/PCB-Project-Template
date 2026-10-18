# Manufacturing

`fabrication/generated` / `assembly/generated` (ignored) hold WIP exports.
When approved, capture named immutable release packages under `releases/`,
including Gerbers, drills, assembly position files, BOM, IPC outputs as
applicable, build notes, source commit and SHA-256 manifests.

Do not edit exported Gerber/drill files manually. Use KiCad output jobs or
KiCad CLI to regenerate from approved design.
