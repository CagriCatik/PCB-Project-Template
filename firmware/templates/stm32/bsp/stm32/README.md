# STM32 BSP integration

STM32CubeMX is optional for PCB work and is only needed to *generate* the MCU
code; building needs only its generated CMake output and the Arm GNU Toolchain.
No MCU, clock tree or pinout is preselected.

1. In STM32CubeMX create the project for your exact MCU/package (pins must match
   the KiCad schematic and `hardware/interfaces/pinmap.csv`).
2. Give the GPIO that drives your status indicator a user label (e.g. `STATUS_LED`).
   If it is called differently, set `FW_STATUS_LED` to that label in the
   `stm32-debug` preset of `firmware/CMakePresets.json`.
3. Project Manager > Toolchain/IDE: **CMake**; generate into `firmware/bsp/stm32/cubemx/`.
   The generated files are used as-is; the kit compensates for CubeMX's
   assumption that it is the CMake root (linker-script path, target order).
4. In a `USER CODE` block of the generated `main.c`, declare
   `void bsp_heartbeat_task(void);` and call `bsp_heartbeat_task();` in the main
   loop. Keep your code inside `USER CODE` blocks so CubeMX regeneration keeps it.
5. Install the Arm GNU Toolchain. It is found on `PATH`, in standard locations
   (`~/Tools/arm-gnu/*/bin`, `~/.local/toolchains/*/bin`,
   `/Applications/ArmGNUToolchain/*/arm-none-eabi/bin`, STM32CubeCLT, STM32CubeIDE),
   or via `ARM_GNU_TOOLCHAIN_BIN=/path/to/bin`. Then run
   `scripts/kit firmware "<project>" --target stm32` from the kit.

The build reports the ELF architecture and FLASH/RAM usage. Moving the project
is handled (stale CMake caches are reconfigured). Host unit tests
(`--target host`) need only CMake and a C compiler. Flashing and hardware
execution are not part of the kit.
