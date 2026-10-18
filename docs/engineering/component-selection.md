# Component selection

## Workflow

1. **State the requirement, not the part.** Example: "3.3 V rail, 600 mA
   continuous from 5 V USB, ambient up to 50 °C" rather than "an LDO".
2. **Shortlist by architecture** (e.g. linear regulator vs. buck converter) using
   the requirement: dissipation `P = (Vin − Vout) · I` for a linear regulator is
   often what rules it out.
3. **Shortlist manufacturer part numbers (MPNs)**, not generic values. A "10 µF
   capacitor" is not a part; a specific MPN with dielectric, voltage rating,
   package and tolerance is.
4. **Review each candidate's datasheet** with [datasheet-review.md](datasheet-review.md).
5. **Check availability and lifecycle** at two or more distributors (stock,
   lead time, lifecycle status such as active / NRND / EOL).
6. **Pick an alternate** where practical (same footprint and pinout, or a
   documented second footprint option) and record it.
7. **Record the decision** in `components/approved-parts/<Manufacturer>__<MPN>.json`
   (`scripts/kit components add`) with datasheet URL and revision, ratings with
   their source page, procurement entries and approval status.
8. **Link the schematic**: set `Manufacturer` and `MPN` fields on the symbol; the
   `component_metadata` and `bom` gates check them against the record.

## Why nominal values are not enough

A part's nominal value says nothing about how it behaves at your operating
point. Typical traps:

- **Ceramic capacitors** lose much of their capacitance under DC bias and with
  temperature (dielectric-dependent). Use the manufacturer's DC-bias data, not
  the printed value.
- **Resistors** have power ratings that derate with temperature, and voltage
  limits independent of power.
- **Regulators and MOSFETs** are often limited by heat, not by their headline
  current rating: the current they can carry depends on copper area, airflow
  and ambient temperature.
- **Logic interfaces** need compatible input thresholds, not just the same
  nominal supply voltage.

## Three different limits

| Limit | Meaning | Use it for |
| --- | --- | --- |
| Absolute maximum ratings | Exceeding them may damage the device; not an operating condition | Fault and transient analysis only |
| Recommended operating conditions | Where the datasheet's characteristics are guaranteed | The design envelope |
| Application-specific limits | Your derating policy and the circuit's real stresses (temperature, ripple, surge, lifetime) | Final selection and margins |

Design inside the recommended operating conditions with a documented margin.
Never design to the absolute maximum ratings.

## Mechanical and thermal checks

- Package and land pattern match the datasheet's recommended footprint (pad
  sizes, exposed pad, pin-1 marking, keep-outs). The `pin_pad_mapping` gate
  catches pins without pads; it cannot check pad *geometry*.
- Height and body size against enclosure and neighbours.
- Operating temperature range covers the product's ambient plus self-heating.
- Thermal resistance figures (θJA, θJC, θJB) are measured on the
  manufacturer's test board; your board differs. Treat derived temperatures as
  estimates (see `docs/THERMAL_ANALYSIS.md` in the kit).

## Recording assumptions

Write down every assumption that influenced a choice (duty cycle, ambient,
airflow, maximum cable length, supply tolerance) in the component record's
`notes` or in `docs/requirements.md`. A later reviewer must be able to see
*why* a part was acceptable, not just *that* it was chosen.

Never invent ratings: if a value is not in the datasheet, mark it as an
assumption or measure it.
