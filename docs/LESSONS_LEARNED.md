# Lessons learned

Findings from implementing and testing against the real KiCad 10.0.7 install
(2026-10-18). Each one changed the code.

1. **The missing IPC socket was a disabled server.** `kicad_common.json` had
   `api.enable_server: false`; KiCad then never creates `/tmp/kicad/api.sock`.
   Diagnostics now read the setting first. Editing it while KiCad runs is
   unsafe because KiCad rewrites the file on exit, so `ipc enable` refuses then.
2. **kicad-cli help is the only reliable capability source.** Usage lines name
   only the last two path components (`Usage: export step ...`), and an unknown
   subcommand silently prints its parent's help with exit code 0. Discovery
   requires a path match; 43 commands are found on 10.0.7.
3. **KiCad's official Arduino template is not KiCad-10 clean.** It references
   `${KICAD9_3DMODEL_DIR}/*.wrl`; 10.0.7 resolves neither the variable nor ships
   VRML, so STEP export silently omitted all four connector models. Generation
   migrates references only where the exact STEP exists and records each change.
4. **KiCad 10 library tables nest.** The global `sym-lib-table` contains a single
   `(type "Table")` entry pointing at the bundled table; resolution must recurse.
5. **Local labels produce `/NAME` nets.** A pcbnew-built board with nets named
   `VIN` fails parity against a schematic with local label `VIN` (`/VIN`).
6. **Byte-identical exports are impossible; normalized ones are not.** Gerber,
   drill, netlist and PDF differ only in timestamps; STEP also reorders entities
   (OpenCascade), so STEP uses an entity census. pcbnew also assigns fresh item
   UUIDs, so regenerating the fixture is semantically, not byte-, identical.
7. **The PCM repository rejects Python's default User-Agent (HTTP 403).** The
   update check sends an explicit agent and verifies the index SHA-256 from
   `repository.json`.
8. **Version strings need padding.** IBOM declares `kicad_version_max: "10"`;
   naive tuple comparison treats `(10,)` < `(10, 0)` and wrongly marked it
   incompatible.
9. **Two PCM databases existed.** `~/Library/Preferences/kicad/10.0/installed_packages.json`
   is current (Freerouting 2.4.1); `~/Documents/KiCad/10.0/3rdparty/installed_packages.json`
   was stale (1.6.2). Only the former is used.
10. **A PCM entry is not a working plugin.** KiKit's PCM package is an action
    shim; the backend is the `kikit` package in KiCad's Python (1.8.1 here).
    Verification therefore invokes each tool on a real board.
11. **Case-insensitive APFS.** Required `docs/ARCHITECTURE.md` collides with an
    existing `docs/architecture.md`; project docs were moved, not overwritten,
    and a test now rejects case collisions anywhere.
12. **Native template identity must be deterministic.** A random schematic UUID
    per build made every reinstall look outdated; installed templates now use a
    UUID derived from the template id, while user projects get fresh UUIDs.
13. **Launchers must not `cd`.** Changing into the kit root broke relative
    project paths given by the user.
14. **Freerouting runs headless with Java 27** although the package names Java 25;
    the check is "≥ 25" and is confirmed by an actual routing run.
15. **Build directories are not sources.** Firmware host builds wrote into
    `firmware/build/`, which the source hash included, so an export after a
    firmware gate reported "source changed". Source hashing now uses the same
    exclusion rules as templates and packaging (`core/common.py`).
16. **Footprint attributes are part of parity.** KiCad's test-point footprint is
    "exclude from BOM" while the symbol is in the BOM; DRC parity flags this.
    A builder must copy symbol attributes onto footprints as *Update PCB from
    Schematic* does.
17. **pcbnew's Python bindings omit the stack-up API in 10.0.7.** Profile
    defaults are authored by pcbnew; only the `(stackup ...)` block is written
    in KiCad's format and verified by re-loading the board in pcbnew.
18. **CubeMX's CMake output assumes it is the build root.** Its package adds
    sources to `${CMAKE_PROJECT_NAME}` (the target must exist first) and its
    toolchain file passes `-T ${CMAKE_SOURCE_DIR}/<script>.ld`. The template's
    first STM32 integration therefore failed at configure time against real
    CubeMX 6.18 output; found only when a real cross-build was attempted.
19. **Installed is not on PATH.** The Arm GNU Toolchain was installed twice in
    user directories but not on PATH; detection now searches standard
    locations and `ARM_GNU_TOOLCHAIN_BIN`, changing PATH only for the build.
20. **CubeMX script mode can hang.** `STM32CubeMX -q` waited indefinitely when
    the `.ioc` had a peripheral not ready for generation; the kit does not
    drive CubeMX.
