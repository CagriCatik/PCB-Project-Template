# Carrier boards and socketed DevKits

These rules apply to ESP32, STM32, Arduino and other plug-in modules. They are
an interface-design checklist, not a ready-made circuit or universal footprint.

## Identify before drawing

Record manufacturer, exact board/model/revision, module marking, flash/PSRAM
variant, antenna type and manufacturer pinout/geometry sources. Similar names
and matching header pitch do not prove compatible pinouts or dimensions.
Compare against the purchased board. Never infer a socket footprint from a photo.

Account for **every physical pad**, not just application GPIOs. Keep:

- `hardware/interfaces/carrier.json`: board identity, pinout source and socket
  references with positive `pad_count` (pads numbered 1..N per socket);
- `carrier-pins.csv`: one row per socket pad, physical module header/pin, GPIO
  identifier if applicable, schematic net, role, restriction, verification and
  source reference. The ESP32 template supplies intentionally empty files;
- existing `pinmap.csv`: reviewed application/firmware mapping derived from the
  schematic. Cross-check assigned rows against the carrier inventory and BSP.

Use `scripts/kit carrier check PROJECT` from the kit checkout. It finds missing,
duplicate/undeclared pads, missing identity/provenance, duplicate GPIOs and
incomplete/contradictory roles. It does **not** resolve the actual netlist,
validate manufacturer truth or check footprint geometry. Follow it with native
`pin_pad_mapping`, schematic review and a physical orientation check. It is a
separate advisory command, not an additional automatic `verify`/release gate.

Example socket declarations for two physical headers:

```json
{"sockets": [{"reference": "J1", "pad_count": 22}, {"reference": "J3", "pad_count": 22}]}
```

A composite socket symbol can instead declare one reference with 44 pads.
This example is a representation choice, not a verified board pinout. Each CSV
row still records the actual module header and pin. Use the schema-1 file from
the ESP32 template and fill the complete identity, not just the example above.

| Role | Meaning / requirement |
| --- | --- |
| assigned | Application GPIO; GPIO id, schematic net and source required |
| reserved | Available for later use; document reason and NC/test-point intent |
| blocked | Unavailable on the selected variant; reason required, no carrier net |
| power / ground | Include every duplicate supply/ground pad and its net |
| reset / boot | Programming or strap function; document external loads and startup state |

`verification` is `documented` or `measured`; neither is inferred by the tool.
A source reference must describe the evidence. Measurements complement, not
replace, the manufacturer's electrical limits. Empty/open rows fail the
inventory check deliberately.

## GPIO selection and startup

Classify chip-family restrictions, memory-reserved pins, strapping pins,
input-only/analogue capabilities, UART/programming/native USB/JTAG needs and
onboard LEDs. Their availability depends on board revision and module variant.
Reserve programming paths before allocating spare GPIOs. Do not apply a classic
ESP32 pin rule unchanged to an ESP32-S3/C3/C6.

For each assigned signal review: direction, voltage domain, output drive or
input limits, boot/reset level, pull resistors, unpowered state, external voltage
and peripheral timing/resource use. MCU GPIO numbers, header numbering and
socket-pad numbers are different fields; never conflate them.

State default behaviour in hardware for reset, bootloader, missing module,
brownout, USB-only power and battery reconnect. Outputs controlling actuators
must have defined inactive defaults. After supply loss/reconnect require the
application's deliberate rearm policy; avoid resuming stale enable commands.
Choose buffer/level-shifter and protection parts from actual limits, including
power-off I/O behaviour. Never rely on a GPIO being high impedance at all times.

## Power domains and connectors

Draw the battery-to-regulators-to-DevKit/peripherals power tree. List which
regulator owns each rail and its load/current/transient budget. Do not feed a
LiPo into a header marked 5V or 3V3. Do not power servos through the DevKit LDO.
Budget the carrier load against the documented DevKit regulator capability.

Review these states separately: carrier on / USB absent, USB only, both
connected, both off, DevKit absent, hot plug and battery reconnect. Confirm
return paths and prevent unintended power through USB, regulator outputs or
GPIO protection structures. Manufacturer-approved supply combinations are
board-specific; adding diode-OR/isolation needs its own validated circuit.
Mark whether the main battery switch leaves USB-powered logic alive.

Place RESET/BOOT buttons according to the exact board schematic: check the
existing pulls/capacitors, polarity and auto-programming circuitry before adding
anything. Do not duplicate or alter the board's strap network by assumption.

## Socket and placement review

Review module top-view versus carrier view, pin-1 marks, header numbering,
orientation, row spacing, standoff/connector height, insertion clearance,
USB/button access, mounting holes and antenna keep-out against manufacturer
geometry. Antenna requirements include copper, components, enclosure and nearby
conductors; derive actual dimensions from the selected module's guide.
Project-local symbols/footprints need pad-by-pad and physical review; no guessed
land patterns or placeholder 3D models count as evidence.
