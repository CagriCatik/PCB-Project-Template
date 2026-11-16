# ESP32 DevKit carrier scaffold

This project starts with a blank KiCad 10.0.7 schematic/PCB. It does not contain
a socket footprint, module pin allocation or a validated regulator. First
complete `hardware/interfaces/carrier.json` and `carrier-pins.csv`, following
`engineering/carrier-guidelines.md`. An empty inventory intentionally fails.

## Firmware path

The supplied optional scaffold uses PlatformIO/Arduino, preserving the common
platform-independent application + BSP interface and CMake host tests. It is
not ESP-IDF integration and does not add LED, servo, IMU or radio drivers.

Run from the kit checkout:

```sh
scripts/kit carrier check /path/to/project
scripts/kit firmware /path/to/project --target host
scripts/kit firmware /path/to/project --target esp32
```

The ESP32 target runs `pio run -e esp32`; PlatformIO and its toolchains are
required. It builds, never uploads. The platform is pinned to `espressif32@8.0.0`.
The baseline board id `esp32-s3-devkitc-1` describes **N8, 8 MB flash, no PSRAM**
in PlatformIO, not N16R8. Change the build/memory/partition settings to match the
purchased board before flashing; a board id alone does not identify its variant.
Record the resolved platform/framework/compiler versions with build evidence.
No cross-build or device execution is implied by the scaffold.

`firmware/bsp/esp32/board_pins.h` initially sets `BSP_STATUS_GPIO` to -1. No GPIO
is driven and status-write attempts return failure until a reviewed indicator
binding is supplied. A simple digital output is not an addressable RGB driver.
Keep safety outputs inactive in hardware and design watchdog/rearm separately.

## ESP32-S3 example restrictions (not a universal pinmap)

Espressif documents multiple DevKitC-1 module/memory variants. In variants with
Octal flash/PSRAM, GPIO35/36/37 are used internally. The v1.1 board also has an
onboard RGB LED on GPIO38. Check the exact revision before allocating either
set of pins; header exposure does not imply free availability. Review boot,
native USB and programming interfaces before application allocation.

Espressif lists USB, 5V header and 3V3 header as mutually exclusive supply
options. Do not assume that simultaneous carrier and USB power is safe; verify
the exact board schematic and any added isolation circuit.

## Primary sources (checked 2026-11-16)

- [Espressif DevKitC-1 v1.1 guide, variant table, headers, power options and linked schematics/geometry](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-devkitc-1/user_guide_v1.1.html)
- [PlatformIO board definition and N8 defaults](https://docs.platformio.org/en/latest/boards/espressif32/esp32-s3-devkitc-1.html)
- [Pinned PlatformIO Espressif32 v8.0.0 release](https://github.com/platformio/platform-espressif32/releases/tag/v8.0.0)

These are reference sources, not evidence that a purchased clone or a socket
has been measured. Record the actual board's source revision and measurements.
