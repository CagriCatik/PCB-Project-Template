# KiCad compatibility

| Item | Value |
| --- | --- |
| Reference and tested version | **KiCad 10.0.7** (release build, macOS arm64) |
| Expected location | `/Applications/KiCad/KiCad.app` (also `~/Applications/KiCad/KiCad.app`) |
| CLI | `<KiCad.app>/Contents/MacOS/kicad-cli`; override with `KICAD_CLI` |
| App bundle / bundled Python | override with `KICAD_APP` / `KICAD_PCBNEW_PYTHON` |
| KiCad 11 / nightly | not supported, not tested, never required |

## Policy

- `tools/kicad/cli.py` runs `kicad-cli version`; the result must be a plain
  version number. Exactly `10.0.7` is **TESTED**.
- Any other version is refused with exit 11 unless `KICAD_KIT_ALLOW_UNTESTED=1`
  is set. Then the checks run, every verification report and manifest records
  `kicad_version_status: "UNTESTED"`, summaries show `UNTESTED VERSION`, and GO
  releases are blocked (exit 22). The version is never changed silently.
- All KiCad-specific operations are isolated in `tools/kicad/` (CLI, IPC, file
  readers, library tables). Commands and flags are used only if the installed
  CLI's `--help` advertises them (`scripts/kit cli capabilities`: 43 on 10.0.7).

## Version-specific facts this kit relies on (10.0.7)

| Fact | Where it matters |
| --- | --- |
| File formats: schematic `20260306`, board `20260206`, symbol library `20251024` | Fixture builder, profile defaults |
| Global library tables contain a nested `(type "Table")` entry to the bundled table | `tools/kicad/libraries.py` |
| `${KICAD10_*}` path variables; `${KICAD9_*}` are **not** resolved by kicad-cli | 3D-model and portability gates, Arduino template migration |
| `kicad-cli` usage lines name only the last two command words; unknown subcommands print the parent's help with exit 0 | Capability discovery |
| PCM database at `~/Library/Preferences/kicad/10.0/installed_packages.json` | Plugin status |
| IPC socket `/tmp/kicad/api.sock` exists only with `api.enable_server: true` | IPC diagnostics |
| pcbnew Python bindings do not expose `BOARD_STACKUP` | Profile stack-up block is written in KiCad's own format and re-read by pcbnew |

## Real integration tests run against 10.0.7

ERC/DRC/parity on the reference projects and on every template, all ten export
types, reproducibility, profile read-back through pcbnew, pad positions versus
pcbnew, relocation of a project with local libraries, InteractiveHtmlBom,
Freerouting and KiKit invocations. GUI interaction and the live IPC API are
**not** covered (see `docs/ACCEPTANCE_REPORT.md`).
