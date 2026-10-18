# Routing guidelines

Each rule is marked:

- **[constraint]** an electrical, datasheet or fabrication requirement: violating
  it can make the board fail or be unmanufacturable;
- **[heuristic]** good practice that is usually right but yields to constraints.

## Stack-up and reference planes

- **[constraint]** Agree the stack-up with the fabricator before routing
  impedance-controlled nets; the template's `2-layer` / `4-layer` profiles are
  examples (`scripts/kit templates profiles`), not a fabricator's stack-up.
- **[constraint]** Every fast signal needs a continuous reference plane on the
  adjacent layer along its whole path. Return current flows under the trace;
  a slot or split in the plane under a fast trace forces a detour that radiates
  and couples. If a signal must change reference layers, place a stitching via
  (or capacitor, for different nets) next to the signal via.
- **[heuristic]** Four-layer default arrangement: signal / ground / power or
  ground / signal. On two-layer boards keep as much of one layer as a solid
  ground as possible.

## Net classes, widths and clearances

- **[constraint]** Track width from current *and* allowed temperature rise
  (IPC-2152 data or a calculation), not from a fixed number; outer and inner
  layers differ. Record the calculation as an estimate.
- **[constraint]** Clearance from voltage (creepage/clearance per the relevant
  safety standard where mains or high voltage is involved) and from the
  fabricator's minimum, whichever is larger.
- **[heuristic]** Put power nets, sensitive nets and impedance-controlled nets
  in their own net classes so the rules are enforced by DRC instead of memory.
  The profiles define `Default` and `Power` as examples.

## Vias

- **[constraint]** Drill and annular ring within the fabricator's capability;
  via current capacity is limited — use several vias for high current and for
  thermal transfer.
- **[heuristic]** Use one via size per function (signal, power, thermal) to keep
  drill counts and cost down.

## Power distribution

- **[constraint]** Route the high-current loop (source → load → return) with
  enough copper for its current and the smallest practical loop area.
- **[heuristic]** Star or planes for power, short wide connections from
  decoupling capacitors to pins and to the ground plane (via close to the pad).

## Ground and copper zones

- **[constraint]** Assign each zone to the correct net; a zone on the wrong net
  or an unintended island is a real defect. Refill zones and check for
  unconnected copper (`drc` gate) after every change.
- **[heuristic]** Avoid splitting ground planes unless a datasheet or standard
  requires it; a single solid ground with careful placement is usually better.
  Remove isolated copper islands or stitch them.
- **[heuristic]** Thermal relief on pads that must be hand-soldered or reflowed
  evenly; solid connection where current or heat transfer matters — a
  deliberate choice per pad class, not a default left unchanged.

## Signals

- **[constraint] Differential pairs** (e.g. USB, Ethernet, LVDS): route as
  coupled pairs with the impedance the interface specifies, length-matched
  *within the pair* to the tolerance the interface standard or transceiver
  datasheet gives. Slower differential buses such as CAN or RS-485 mainly need
  a coupled pair and correct termination; apply tighter rules only where the
  transceiver datasheet asks for them.
- **[constraint] Length matching between signals** only where a specification
  defines a timing budget (e.g. DDR, parallel high-speed buses). Do not
  length-match SPI, I²C, UART or GPIO "to be safe": at their edge rates it buys
  nothing and costs space and coupling.
- **[heuristic] Clocks and fast edges:** short, over an unbroken reference,
  away from board edges and from sensitive analog nets; series termination near
  the driver if the datasheet recommends it.
- **[heuristic] SPI / I²C:** keep lines short and together with their ground
  return; I²C pull-up values come from bus capacitance and speed (I²C
  specification), not habit.
- **[constraint] Analog:** follow the device's layout section (Kelvin
  connections for current sense, guard rings for high impedance, reference
  routing); keep digital return currents out of the analog path.
- **[heuristic] Corners:** 45° corners or arcs are a manufacturing and
  aesthetic convention. A 90° corner is **not** an electrical defect at the
  frequencies of typical boards; avoid acute angles (acid traps on some
  processes) rather than 90° ones.

## Silkscreen and solder mask

- **[constraint]** No silkscreen on pads; solder-mask web and expansion within
  the fabricator's limits (DRC checks the configured values).
- **[heuristic]** Readable reference designators (text height/thickness at or
  above the fabricator's minimum), pin-1 and polarity marks that remain visible
  after assembly, connector pin labels on the silkscreen.

## After routing

1. DRC with zero unconnected items and zero unreviewed violations; schematic
   parity clean.
2. Every DRC exclusion has a written reason in the review record.
3. Re-check the critical loops and reference planes visually; DRC does not
   understand return paths.
