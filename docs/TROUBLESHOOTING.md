# Troubleshooting

Start with `scripts/kit doctor`; it reports every area with a cause.

| Symptom | Cause and fix |
| --- | --- |
| `KiCad 10.0.7 required; ... reports '10.0.8'` but you want to try anyway | Set `KICAD_KIT_ALLOW_UNTESTED=1`: checks run, reports say `UNTESTED`, GO releases stay blocked (`docs/KICAD_COMPATIBILITY.md`). |
| `portability` gate: absolute path / user-defined variable | A library table, 3D model or sheet points outside the project. Move the file under `hardware/libraries/` and use `${KIPRJMOD}`; see `docs/LIBRARY_MANAGEMENT.md`. |
| `pin_pad_mapping`: symbol pin(s) without a pad | The footprint does not fit the symbol (wrong package or pin numbering). Assign the correct footprint; do not renumber pins to silence it. |
| `scripts/kit releases` shows STALE or MODIFIED (exit 21) | Sources or exported files changed after the export. Re-export under a new revision; never send a STALE/MODIFIED package. |
| `designator_consistency FAILED` | BOM, placement file, schematic and board disagree; update the PCB from the schematic in KiCad, then re-export. |
| `kicad-cli not found` (exit 10) | KiCad is not in `/Applications/KiCad/` or `~/Applications/KiCad/`. Install 10.0.7 (`scripts/install-kicad.sh --dmg FILE`) or set `KICAD_CLI` / `KICAD_APP`. |
| `KiCad 10.0.7 required; ... reports '10.0.x'` (exit 11) | Another KiCad version answers. The kit is pinned; install 10.0.7 side by side with `--dest "$HOME/Applications/KiCad"` and set `KICAD_APP`. |
| Many `Fontconfig warning:` lines in raw output | A Homebrew fontconfig configuration is picked up by KiCad. Harmless; summaries filter these lines, raw records keep them. |
| New project fails DRC with `invalid_outline` | Blank templates have no board outline. Draw one on `Edge.Cuts`. Expected behaviour. |
| Arduino Shield fails ERC/DRC immediately | KiCad's official `Arduino_Uno` template ships with 26 ERC findings (unpowered power pins, isolated labels) and 4 unconnected items on 10.0.7. They disappear as the shield circuit is designed. |
| `models_3d` reports `KICAD9_3DMODEL_DIR` | KiCad 10.0.7 does not resolve KiCad 9 variables. Point the model to `${KICAD10_3DMODEL_DIR}/...step` (the Arduino template is migrated automatically where the STEP exists). |
| `Close the project before automation; lock files found` (exit 14) | The design is open in KiCad. Save and close it, or remove a stale `~*.lck` after a crash. |
| `ipc status` UNAVAILABLE, `api.enable_server: False` | Enable **Preferences > Plugins > Enable KiCad API** and restart KiCad, or quit KiCad and run `scripts/kit ipc enable --apply`. |
| `ipc enable` refuses (exit 16) | KiCad is running; it would overwrite the setting on exit. Quit KiCad first. |
| IPC enabled but no `/tmp/kicad/api.sock` | Restart KiCad after enabling; the server starts with KiCad. A leftover socket without a process is stale. |
| `client_missing` | `.venv` lacks `kicad-python`; re-run `./install_template.command` (needs network). |
| Freerouting `VERIFICATION_FAILED: Java 25+ required` | Install a Java ≥ 25 runtime (for example Eclipse Temurin) and re-run `scripts/kit plugins verify freerouting`. |
| KiKit `SHIM_ONLY` | The PCM package is only an action shim; install the `kikit` package into KiCad's Python (`scripts/kit plugins guide kikit`). |
| `plugins updates` UNAVAILABLE | Offline, blocked by a proxy, or the PCM index failed its SHA-256 check. Retry later; installed plugins are unaffected. |
| Plugin versions look old | A stale `~/Documents/KiCad/10.0/3rdparty/installed_packages.json` exists; the kit reads `~/Library/Preferences/kicad/10.0/installed_packages.json` and notes the stale file. |
| `Destination exists and is not an empty directory` (exit 18) | The kit never merges into existing folders. Choose a new path or an empty directory. |
| `Firmware target ... needs: arm-none-eabi-gcc` (exit 17) | Install the Arm GNU toolchain; for Arduino install PlatformIO (`pipx install platformio`). Host tests need only CMake and a C compiler. |
| `arm-none-eabi-gcc (not on PATH and not in: ...)` | Install the Arm GNU Toolchain, or point `ARM_GNU_TOOLCHAIN_BIN` at its `bin/` (no global PATH change needed). |
| STM32 build: `'<label>_Pin' undeclared` | `FW_STATUS_LED` in the `stm32-debug` preset does not match the CubeMX GPIO user label. |
| STM32 build: undefined reference from `main.c` USER CODE | Code inside USER CODE blocks calls functions that are not part of the project (e.g. an old `app.c`); move them to `firmware/app` or remove the call. |
| STM32CubeMX `-q` script hangs after `IP not ready for code generation` | The `.ioc` has an incomplete peripheral configuration; fix it in the CubeMX GUI. The kit never runs CubeMX itself. |
| `STM32CubeMX project missing` during `--target stm32` | Generate a CMake project with STM32CubeMX into `firmware/bsp/stm32/cubemx` (see that folder's README). |
| `Export destination already exists` (exit 21) | Revisions are immutable; use a new `--revision`. |
| `A GO release requires explicit authorization` / `Release requires ... clean Git` (exit 22) | See `docs/MANUFACTURING.md`; drafts need neither. |
| `install_template.command` cannot be opened from Finder | Gatekeeper quarantine on downloaded files: run it once from Terminal, or `xattr -d com.apple.quarantine install_template.command`. |
| Template missing in KiCad's template dialog | Check `scripts/kit templates status`; a different `KICAD_USER_TEMPLATE_DIR` in **Preferences > Configure Paths** moves the directory. |
