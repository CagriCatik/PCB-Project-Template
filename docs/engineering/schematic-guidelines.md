# Schematic guidelines

The schematic is the electrical source of truth: the board, BOM and firmware pin
map derive from it. Its job is to be **correct and readable**, not to look like
the PCB. Logical arrangement (signal flow, function) is independent of physical
placement; never move schematic symbols to mimic the layout.

## Structure

- **Hierarchy by function.** Root sheet = block diagram: one hierarchical sheet
  per function (power input/protection, regulation, MCU, each interface or
  sensor group, connectors). Keep a sheet to one page that can be read at A4/A3.
- **Root-sheet content:** sheet symbols, the interfaces between them, and a short
  note on supply domains. No loose circuitry.
- **Signal flow:** inputs left, outputs right; higher voltages top, ground bottom.
- **Cross-sheet interfaces:** hierarchical pins/labels with direction (input,
  output, bidirectional, power). Global labels only for genuinely global nets
  (e.g. power rails), so a net's scope is obvious.

## Power

- Use power symbols for rails, with names that state the voltage and domain
  (`+3V3`, `+5V_USB`, `VBAT`, `GND`, `AGND`). Keep the same name everywhere.
- Every power net driven only by passive parts or connectors needs a
  **PWR_FLAG** so ERC knows it is driven; add it deliberately at the real
  source (connector, regulator output), not to silence an error elsewhere.
- Show decoupling next to the pin it serves, with value, voltage and dielectric
  in the value or fields; group by supply pin as the datasheet does.
- Put protection (reverse polarity, ESD, fuses, TVS) on the sheet where the
  energy enters, so the protected path is visible.

## Nets and labels

- Name every net that matters for review, debugging or firmware (`I2C_SDA`,
  `MOTOR_EN`, `VSENSE_BAT`); unnamed nets get meaningless auto-names in
  netlists and BOM tools.
- Active-low signals get a consistent marker (`RESET_N` or `~{RESET}`), one style
  per project.
- Mark every intentionally unused pin with a **no-connect flag**. An unmarked
  open pin is either an error or an undocumented decision.
- Connector pins: name the net at each pin and note mating-side orientation
  (pin 1, view direction) in a text note. Keep pin numbering identical to the
  footprint and to `hardware/interfaces/pinmap.csv`.

## Annotation and fields

- Reference designators by class (R, C, L, D, Q, U, J, TP, FB, Y, SW) and
  annotated per sheet or globally; never reuse one after deletion in a released
  revision without noting it.
- Fields on every real part: `Footprint`, `Datasheet` (URL), `Manufacturer`,
  `MPN`; the kit's metadata and BOM gates read these names.
- Add functional annotations where intent is not obvious: "sets 3.3 V:
  Vout = 0.8 V · (1 + R1/R2)", "RC = 1 ms debounce", "test point for scope".
- Place **test points** on rails, resets, boot pins and key buses; they cost
  little and make bring-up measurable.

## Readable versus unreadable

| Unreadable | Readable |
| --- | --- |
| One giant sheet, wires crossing the whole page | Functional sheets, each fitting on a page |
| Nets named `Net-(U3-Pad14)` | `SPI_MOSI`, `+3V3_SENSOR` |
| Decoupling capacitors in a corner "somewhere" | Capacitors drawn next to the supply pin they decouple |
| Labels without direction joining distant sheets | Hierarchical pins with direction on sheet symbols |
| Open pins without flags | No-connect flags on every intentionally unused pin |
| Values like `10u` without voltage/dielectric | `10uF 16V X7R` plus MPN field |
| Symbols arranged like the PCB layout | Symbols arranged by signal flow |

## Before leaving the schematic

1. ERC with zero unreviewed errors and warnings (`scripts/kit verify`); every
   exclusion has a written reason.
2. Every symbol has a footprint whose pads cover all its pins (`pin_pad_mapping`).
3. Datasheet checklists completed for every non-trivial part.
4. Power tree reviewed: each rail's source, maximum load and protection.
