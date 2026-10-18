# Optional firmware workflows

Firmware is optional. Generic PCB projects have no firmware build. The STM32
Embedded and Arduino Shield templates add a CMake host-test setup, a
platform-independent `app/` module and a target BSP; no MCU, pinout or vendor
code is invented.

Run from the kit checkout (`<project>` is the generated project directory):

```sh
scripts/kit firmware "<project>" --target host      # CMake + C compiler: build app/, run unit tests
scripts/kit firmware "<project>" --target stm32     # needs STM32CubeMX output + arm-none-eabi-gcc
scripts/kit firmware "<project>" --target arduino   # needs PlatformIO (pio run -e uno)
```

A missing toolchain is reported as `MISSING_TOOLCHAIN` (exit code 17), never as
a pass. Results are written to `qa/generated/firmware/<target>.json`. Enable the
`firmware` gate in `qa/verification.json` to make host tests part of
`scripts/kit verify`.

- **STM32:** generate a CMake project with STM32CubeMX into
  `firmware/bsp/stm32/cubemx/`; see `firmware/bsp/stm32/README.md`. The Arm
  GNU Toolchain is found on `PATH`, in standard install locations or via
  `ARM_GNU_TOOLCHAIN_BIN`; the status-LED label is set with `FW_STATUS_LED`.
- **Arduino:** `firmware/platformio.ini` targets the Uno (`atmelavr`, `uno`).

Neither workflow flashes hardware. Pin assignments follow the KiCad schematic
and the reviewed `hardware/interfaces/pinmap.csv`.
