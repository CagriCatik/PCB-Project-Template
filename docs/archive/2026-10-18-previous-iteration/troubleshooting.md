# Troubleshooting

- **Missing embedded-hw-fw source:** use the repository root. The repaired
  `.command` installer no longer expects a child folder. Keep original files.
- **Template is missing from KiCad:** select the installed parent with Browse
  in File > New Project, or set `KICAD_USER_TEMPLATE_DIR` in Configure Paths.
  `meta/info.html` remains template metadata, not kit configuration.
- **Installer refuses changed source:** this is conservative version handling.
  Install to another parent; do not delete the old tree to force an update.
- **Python missing in Finder:** install Python 3.10+ from its official distribution
  and ensure `python3` is on PATH, or invoke the `.command` from a terminal with
  `KICAD_KIT_PYTHON` set to the absolute interpreter path.
- **KiCad version mismatch:** set `KICAD_CLI` to 10.0.7. The application installer
  never silently upgrades/downgrades or replaces an existing destination.
- **Verification exit 20:** inspect the recorded ERC/DRC JSON. A fresh blank PCB
  normally reports `invalid_outline`. Draw the actual outline in KiCad; do not
  waive the error merely to make a new template appear clean.
- **IPC unavailable:** use the optional environment and check API enablement,
  open board and actual socket. Importing `kipy` alone does not prove reachability.
- **Plugin is present but not listed:** restart PCB Editor, inspect its plugin
  error messages and `pcbnew.PLUGIN_DIRECTORIES_SEARCH`. Presence on disk does
  not prove compatibility or runtime dependencies. PCM owns PCM updates.
- **FreeRouting Java errors:** diagnostics reports the real installed runtime;
  use the exact router release's Java requirements, not an assumed global minimum.
- **Locked project:** close the editor/manager. The kit does not remove locks
  or guess whether an unsaved designer state should be discarded.
- **STEP fails:** supply a real closed outline, inspect geometry and actual model
  paths. Draft manifests retain failed command output and never label it GO.
- **VS Code cannot launch:** install the app or its `code` shell command. The
  adapter reports actual launch errors and does not install an editor implicitly.
- **Native tests cannot import pcbnew:** set `KICAD_PCBNEW_PYTHON` to KiCad's own
  interpreter. Host `python3` is for the kit, not legacy KiCad scripting.
- **Fontconfig warnings on this Mac:** the CLI can emit warnings from Homebrew
  font configuration. They are retained in command logs; ERC/DRC decisions use
  KiCad's return status and structured reports.
