# {{PROJECT_NAME}}

KiCad {{KICAD_VERSION}} project created from the **{{TEMPLATE_TITLE}}** template
of PCB-Project-Template {{KIT_VERSION}} on {{CREATED}}.

| Path | Owns |
| --- | --- |
| `{{PROJECT_NAME}}.kicad_pro/.kicad_sch/.kicad_pcb` | Native KiCad project (hardware truth) |
| `hardware/` | Custom libraries (`${KIPRJMOD}`), interfaces, constraints, mechanical, simulation |
| `firmware/` | Optional firmware, BSP and drivers |
| `components/` | Component records, datasheets, SPICE models |
| `manufacturing/` | Release checklist, approvals, generated exports |
| `docs/` | Requirements, architecture, interfaces, bring-up, decisions |
| `qa/` | Verification configuration, design reviews, reports |

## Everyday commands (run from the kit checkout)

```sh
scripts/kit verify  "<this project>"                 # ERC, DRC, parity, libraries, metadata, 3D, BOM
scripts/kit export  "<this project>" --revision A1   # NO-GO draft manufacturing outputs
scripts/kit open    "<this project>" --kicad         # or --vscode
```

Or double-click `project-manager.command` in the kit. A clean ERC/DRC run is a
tooling result only; it does not establish electrical, thermal or fabrication
readiness. See `AGENTS.md` for the rules that apply to automated edits.
