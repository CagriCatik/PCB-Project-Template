# Project templates

| Template | Base design | Firmware |
| --- | --- | --- |
| `generic-pcb` | Blank KiCad 10.0.7 project (`hardware/native-defaults`) | none |
| `stm32-embedded` | Blank KiCad 10.0.7 project | CMake host tests + STM32CubeMX integration point |
| `arduino-shield` | KiCad's official `Arduino_Uno` template, copied from the installed KiCad at generation time | PlatformIO (`uno`) + host tests |

- `skeleton.json` lists the kit paths copied into every project.
- `<id>/template.json` selects the base design, firmware overlays (from
  `firmware/templates/`) and verification gate overrides.
- `<id>/meta/info.html` is KiCad's template metadata, shown in
  **File > New Project from Template**.
- `project-root/` holds the project `README.md` and `AGENTS.md`; `{{...}}`
  placeholders are filled at generation time.

`scripts/kit templates install` installs all three into KiCad's user template
directory; `scripts/kit create` builds an independent project from the same code.
