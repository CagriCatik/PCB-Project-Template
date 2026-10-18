# GUI acceptance checklist (manual)

**Status: NOT_TESTED.** The KiCad graphical interface has not been exercised
automatically: this environment has no safe GUI automation, and opening KiCad
windows on the developer's desktop could interfere with their own KiCad
session. CLI and pcbnew checks (see `docs/ACCEPTANCE_REPORT.md`) do **not**
count as GUI acceptance.

Perform once per KiCad version and after template changes. Takes about 15 minutes.
Save and close your own KiCad work first.

## Preparation

```sh
./install_template.command                      # templates must report INSTALLED / UNCHANGED
scripts/kit create --template generic-pcb    --profile 4-layer --name "GUI Four"   --dest "$HOME/Desktop/gui test/GUI Four"
scripts/kit create --template arduino-shield                    --name "GUI Shield" --dest "$HOME/Desktop/gui test/GUI Shield"
cp -R qa/fixtures/custom-lib "$HOME/Desktop/gui test/custom-lib"
```

## Checks

| # | Action | Expected | Result |
| --- | --- | --- | --- |
| 1 | KiCad > *File > New Project from Template*, *User templates* (or your configured template path) | `Generic PCB`, `STM32 Embedded`, `Arduino Shield` listed with their description pages | |
| 2 | Create `GUI From Template` from `Generic PCB` into an empty folder | Project opens; files renamed to `GUI From Template.*`; `meta/` not copied | |
| 3 | Open `GUI Four/GUI Four.kicad_pro` | Project opens without migration or "file was created by a newer version" dialogs | |
| 4 | Open the Schematic Editor | No missing-library or rescue dialogs; title block shows `GUI Four`, rev `A` | |
| 5 | Open the PCB Editor | Opens without warnings; title block shows the project name | |
| 6 | *Board Setup > Board Stackup* | 4 copper layers, 1.6 mm; dielectric 1/2/3 = prepreg 0.1 / core 1.24 / prepreg 0.1 mm | |
| 7 | *Board Setup > Net Classes* | `Default` (0.2 mm track, 0.15 mm clearance) and `Power` (0.5 mm) | |
| 8 | *Board Setup > Constraints* | Minimum track 0.1 mm, clearance 0.1 mm, via 0.45 mm, hole 0.2 mm | |
| 9 | Open `custom-lib/custom-lib.kicad_pro`, Schematic Editor | TP1/TP2 from `Project_Symbols` shown, no missing-symbol markers; *Preferences > Manage Symbol Libraries > Project* lists `${KIPRJMOD}/hardware/libraries/...` | |
| 10 | PCB Editor of `custom-lib` | TP1/TP2/R1 footprints present; *Inspect > Design Rules Checker* with *Test for parity* shows 0 errors | |
| 11 | *View > 3D Viewer* (custom-lib, then GUI Shield) | Viewer opens; R1 and the shield headers show models; TP1/TP2 have none (expected, reported by `models_3d`) | |
| 12 | Close all without saving | No unexpected "save changes?" prompts on untouched files | |

Record the result (PASS/FAIL + notes), KiCad version and date in
`qa/design-reviews/` and update the GUI status in `docs/ACCEPTANCE_REPORT.md`.
Any FAIL keeps the template acceptance at CONDITIONAL.
