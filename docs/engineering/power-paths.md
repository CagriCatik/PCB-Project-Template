# DC power paths in the routed copper (estimate)

`scripts/kit power paths PROJECT [--case ID ...] [--grid MM] [--region X1 Y1 X2 Y2]` estimates how a
DC load current spreads through the actual copper of one net: filled zones, tracks, via rings, pads and
plated holes between the layers. It reports the voltage at every sink relative to the source, the copper
loss, the vias and plated holes that carry more than 50 mA, the highest linear current densities
(A per mm of copper width) per layer, and writes one colour map per layer.

Use it after routing a power or return path, to find necks, overloaded vias and unequal via sharing. It is
an **estimate**: DC, 20 °C, copper thickness from the board stack-up, stated plating, no temperature rise.
Confirm drops and temperatures on the built board.

## Inputs

Cases live in `hardware/simulations/power/current-paths.json`. Every number references
`hardware/interfaces/assumptions.json` (see [design-contracts.md](design-contracts.md)); nothing is built in.

```json
{
  "schema": 1,
  "plating": "HOLE_PLATING_MIN",
  "cases": [
    {"id": "input", "net": "/Power/VBAT_IN", "layers": ["F.Cu", "B.Cu"],
     "source": [["J1", "2"]],
     "sinks": [{"label": "fuse input", "pads": [["F1", "1"]], "current": "I_INPUT_MAX"}]},
    {"id": "return", "net": "GND", "layers": ["F.Cu", "In1.Cu", "In2.Cu", "B.Cu"],
     "source": [["J1", "1"]],
     "sinks": [{"label": "load return", "pads": [["J2", "2"]], "current": "I_LOAD", "direction": "in"}]}
  ]
}
```

- `plating`: an assumption in `mm` (hole-wall copper thickness, e.g. the fabricator's minimum or the
  IPC class you order). It sets the via/plated-hole barrel resistance.
- `source`: pads held at 0 V. `sinks`: pads that draw (`direction: "out"`, default) or feed
  (`"in"`, return currents) the referenced current in `A`.
- `layers`: copper layers to model. Layers left out are not part of the path.
- The board needs a stack-up with copper thickness (Board Setup > Physical Stackup).

## Model and limits

KiCad's bundled Python (pcbnew) turns the net's copper into polygons; the kit rasterises them on a square
grid (`--grid`, default 0.1 mm) and solves the resistor network with scipy. Every terminal pad is
equipotential; vias join layers through the barrel resistance between the layer centres.

Not modelled: temperature rise and copper heating, plating and etch tolerance, solder-filled holes, AC
effects/ripple, connector contact resistance. Necks narrower than a few grid cells are coarse; repeat
with a finer grid (or a `--region`) before relying on a value there. A disconnected sink is reported
as `UNCONNECTED_SINKS` (exit 20), not silently ignored.

Evidence: `qa/generated/power-paths/run-*/result.json` with board, case file and assumption hashes,
the input basis and the maps.
