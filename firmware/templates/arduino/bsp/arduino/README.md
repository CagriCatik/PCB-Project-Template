# Arduino BSP

`bsp_arduino.cpp` implements `bsp/board_io.h` with the Arduino core. Build with
PlatformIO (`pio run -e uno` in `firmware/`). The application module in
`firmware/app` stays free of Arduino headers and is unit-tested on the host via
`scripts/kit firmware "<project>" --target host`.
