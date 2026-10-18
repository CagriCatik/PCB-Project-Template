# ADR-0001: KiCad core files in project root

Status: Accepted for template

Context: Native KiCad project templates rename core files based on template
name; top-level `.kicad_pro`, `.kicad_sch`, and `.kicad_pcb` maximize tooling
compatibility. PCB design belongs to one logical board by default.

Decision: Keep the native core files at the repository root; `hardware/` holds
supporting assets. A future multi-PCB product can use independent subprojects
under `hardware/boards/` with an explicit migration ADR (not two competing
main project files).

Consequences: Easy native KiCad template selection and code-agent discovery;
a clear place for shared firmware, docs and fabrication release records.
