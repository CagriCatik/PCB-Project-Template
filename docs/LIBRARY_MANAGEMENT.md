# Library management

## Where libraries live

| Kind | Location | Referenced as |
| --- | --- | --- |
| KiCad official symbols/footprints/3D models | KiCad installation | global tables, `${KICAD10_SYMBOL_DIR}`, `${KICAD10_FOOTPRINT_DIR}`, `${KICAD10_3DMODEL_DIR}` |
| Project-specific symbols | `hardware/libraries/symbols/*.kicad_sym` | project `sym-lib-table`, `${KIPRJMOD}/hardware/libraries/symbols/...` |
| Project-specific footprints | `hardware/libraries/footprints/*.pretty/` | project `fp-lib-table`, `${KIPRJMOD}/hardware/libraries/footprints/...` |
| Project-specific 3D models | `hardware/libraries/3d-models/` | footprint `model` path `${KIPRJMOD}/hardware/libraries/3d-models/...` |

Everything a project needs beyond KiCad's own libraries is inside the project
and referenced through `${KIPRJMOD}`, so the project keeps working when it is
moved, renamed, cloned or opened on another machine.

```mermaid
flowchart TD
    subgraph DesignLayer ["1. Schematic &amp; Layout References"]
        SYM["Schematic Symbol<br/><code>lib_id: Project_Parts:U1</code>"]
        FP["PCB Footprint<br/><code>Project_Footprints:QFN-24</code>"]
        M3D["Footprint 3D Model<br/><code>model path: *.step</code>"]
    end

    subgraph TableResolution ["2. Relocatable Project Tables (${KIPRJMOD})"]
        SYM_TAB["sym-lib-table<br/><code>${KIPRJMOD}/hardware/libraries/symbols/...</code>"]
        FP_TAB["fp-lib-table<br/><code>${KIPRJMOD}/hardware/libraries/footprints/...</code>"]
        M3D_PATH["In-tree Model Reference<br/><code>${KIPRJMOD}/hardware/libraries/3d-models/...</code>"]
    end

    subgraph ProjectStorage ["3. In-Tree Storage (Git Versioned)"]
        SYM_FILE["hardware/libraries/symbols/*.kicad_sym"]
        FP_DIR["hardware/libraries/footprints/*.pretty/"]
        STEP_FILE["hardware/libraries/3d-models/*.step"]
    end

    subgraph QualityGates ["4. Automated Verification Gates"]
        GATE_REF["Gate: library_references<br/>All symbols, footprints &amp; pins resolve"]
        GATE_PORT["Gate: portability<br/>Zero machine-dependent or absolute paths"]
    end

    SYM --> SYM_TAB
    FP --> FP_TAB
    M3D --> M3D_PATH

    SYM_TAB --> SYM_FILE
    FP_TAB --> FP_DIR
    M3D_PATH --> STEP_FILE

    SYM_FILE --> GATE_REF
    FP_DIR --> GATE_REF
    STEP_FILE --> GATE_REF

    GATE_REF --> GATE_PORT
```

## Adding a library or part

1. Put the library file/folder under `hardware/libraries/`.
2. Register it without touching existing entries:
   `scripts/kit libraries register "<project>" --kind footprint --name My_Footprints --source "<project>/hardware/libraries/footprints/My_Footprints.pretty"`
3. For a part copied from another library (vendor or KiCad), copy the item into
   the project library, keep its 3D-model reference portable, and record
   provenance and license (example: `qa/fixtures/custom-lib/hardware/libraries/ATTRIBUTION.md`).
   Do not bundle vendor models or datasheets unless their license allows
   redistribution; otherwise record the download URL in `components/sources.csv`.
4. Never replace a symbol or footprint in an existing project silently: changed
   parts are new library items or a reviewed change.

## Checks

| Gate | Detects |
| --- | --- |
| `library_references` | Symbol/footprint nicknames not in any table, missing library files, items not in the library, unresolved variables |
| `portability` | Absolute paths, home-directory paths, user-defined or legacy (`${KICAD9_*}`) variables, relative URIs without `${KIPRJMOD}` in tables, models and sheets |
| `pin_pad_mapping` | Symbol pins (except no-connect pins) without a matching pad number in the assigned footprint |
| `footprint_assignment` | Placed symbols without a footprint |
| `models_3d` | Footprints without a 3D model, or with a model path that does not resolve to a file |

`scripts/kit libraries check` resolves every global and project library.
The `qa/fixtures/custom-lib` reference project is moved to a path with spaces
and non-ASCII characters in the tests and must still pass these gates.

## What the checks cannot do

They cannot verify that a pad *geometry* matches the vendor's recommended land
pattern, or that a 3D model is dimensionally correct. Compare new footprints
and models against the vendor drawing during review (see
`docs/engineering/component-selection.md`).
