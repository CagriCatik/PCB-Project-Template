# Firmware

The template is toolchain-neutral: STM32Cube + CMake, Zephyr, ESP-IDF,
Arduino, or other builds are NOT mixed by default. Select one target and
record toolchain pinning in docs/architecture.md.

- `app/`: target-independent application behavior, state machines, protocols.
- `bsp/`: board-specific pin definitions, clock trees, startup and vendor HAL.
- `drivers/`: stable interfaces, concrete peripheral/device adapters.
- `config/`: reviewed build configuration (not unverified pin assignments).
- `tests/`: host tests, mocks, embedded/HIL tests where applicable.
- `tools/`: flashing/debug helpers with explicit target and safety checks.

Hardware is authoritative for pinouts; firmware config tracks the reviewed
`hardware/interfaces/pinmap.csv` contract.
