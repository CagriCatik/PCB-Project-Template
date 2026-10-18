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
graph TD
    subgraph Schematic ["Schaltplan-Ebene"]
        SYM["Symbol lib_id:<br/>'Project_Parts:U1'"]
        SYM_TABLE["sym-lib-table"]
    end

    subgraph Board ["Layout-Ebene"]
        FP["Footprint-Referenz:<br/>'Project_Footprints:QFN-24'"]
        FP_TABLE["fp-lib-table"]
        MODEL_REF["3D-Modell Pfad"]
    end

    subgraph Resolution ["Auflösung & Portabilitätsprüfung"]
        KIPRJMOD["${KIPRJMOD} Basisverzeichnis<br/>(Projekt-lokal & relocatable)"]
        CHECK_ABS{"Absolute Pfade /<br/>Home-Dir oder ${KICAD9_*}?"}
    end

    subgraph Storage ["hardware/libraries/"]
        SYM_FILE["symbols/*.kicad_sym"]
        FP_DIR["footprints/*.pretty/"]
        STEP_FILE["3d-models/*.step"]
    end

    SYM --> SYM_TABLE
    FP --> FP_TABLE
    
    SYM_TABLE -->|Präfix '${KIPRJMOD}'| SYM_FILE
    FP_TABLE -->|Präfix '${KIPRJMOD}'| FP_DIR
    MODEL_REF -->|Präfix '${KIPRJMOD}'| STEP_FILE

    KIPRJMOD --> CHECK_ABS
    CHECK_ABS -->|Ja| GATE_FAIL["Gate portability: FAIL<br/>(Nicht portabel)"]
    CHECK_ABS -->|Nein| GATE_PASS["Gate portability: PASS<br/>(Git clone- & teamfähig)"]
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
