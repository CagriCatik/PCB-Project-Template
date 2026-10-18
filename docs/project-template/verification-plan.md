# Verification and release gates

| Gate | Evidence | Status |
|------|----------|--------|
| Requirements / interface review | traced requirements + peer review | OPEN |
| ERC | CLI report 0 unwaived errors/warnings | OPEN |
| DRC + schematic parity | CLI report 0 unwaived errors/warnings | OPEN |
| Netlist / no-connect audit | reviewed differences and 0 unintended unrouted nets | OPEN |
| Power / thermal / PCB copper | calculations with worst cases and margins | OPEN |
| Datasheets / footprint / pin 1 | manufacturer sources and physical review | OPEN |
| Mechanical clearance / real 3D | interference review and source provenance | OPEN |
| Firmware static + host + interface tests | reports with pinned toolchain | OPEN |
| Prototype bring-up / measurements | current, power, temperatures, I/O | OPEN |
| BOM availability / manufacturing | signed release checklist | OPEN |

An empty PCB can pass DRC and still be NOT a valid design. Simulation alone does
not sign off a power path. Record approved DRC/ERC exclusions explicitly.
