# Baseline audit

The repository root is the native template, not an `embedded-hw-fw/` child. All current source is retained. Initial Git status and hashes are recorded in `baseline-inventory.json`; an untouched working copy was saved outside the repository at `/tmp/pcb-template-preservation-baseline` during implementation.

Existing installer and tests point to the absent child directory. The installer therefore fails before copying; tests fail on missing metadata and domain files. `.gitattributes` is referenced by tests but absent. Documentation also mentions the absent child. These paths will be repaired in place.

Reusable: all domain documentation and CSV contracts, native metadata, macOS DMG installer, pinned InteractiveHtmlBom installer behavior, verification command flags, agent and release rules. `README Kopie.md` was reviewed: it is useful generated-project onboarding and is preserved byte-for-byte. No native project files currently exist; native KiCad generates its own blank design when using the GUI template.

Additive modules will own copying, project registration, diagnostics, library tables, CLI verification and release evidence. Shell entrypoints delegate to these modules. Existing entrypoint originals and hashes are recorded before narrow compatibility repairs. No global apps or plugin trees will enter generated projects.

## Later authorized documentation cleanup

After reviewing the duplicate, the user explicitly authorized removing
`README Kopie.md`. Its directory guide, first development steps and source-data
rules were consolidated into the main README. The original baseline inventory
remains unchanged as a historical record; preservation tests name this one
intentional retirement explicitly.
