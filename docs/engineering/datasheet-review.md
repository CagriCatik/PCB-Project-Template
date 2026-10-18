# Datasheet review checklist

Copy this checklist into `qa/design-reviews/` (one file per part or per
function) and fill it in before the part is placed in the schematic. Record the
datasheet revision and the page/figure for every answer. Do not fill in values
the datasheet does not give: mark them `ASSUMPTION` or `TO MEASURE`.

Part: ________________  MPN: ________________  Datasheet revision/date: ________

## Electrical

- [ ] Supply voltage range (recommended operating) and absolute maximum — p.__
- [ ] Supply sequencing / ramp-rate / power-on-reset requirements — p.__
- [ ] Current consumption: typical, maximum, and peaks (start-up, radio TX, inrush) — p.__
- [ ] Maximum output / load currents per pin and per package — p.__
- [ ] Interface voltage levels (VIH/VIL, VOH/VOL) versus connected devices — p.__
- [ ] Pins that are not 5 V tolerant, or tolerant only when powered — p.__
- [ ] Required external components (pull-ups, bias resistors, crystals, inductors) — p.__
- [ ] Recommended reference / application circuit — p.__
- [ ] Decoupling and bulk capacitance: values, dielectric, placement notes — p.__
- [ ] Filtering requirements (ferrites, RC on reference or analog supplies) — p.__
- [ ] ESD / surge ratings and needed external protection — p.__

## Pins and behaviour

- [ ] Pin configuration and package view (top or bottom view?) — p.__
- [ ] Pin states during reset and start-up; boot-strapping pins — p.__
- [ ] Unused-pin handling (tie, float, NC) — p.__
- [ ] Exposed / thermal pad connection (net, vias) — p.__

## Thermal

- [ ] Operating and junction temperature limits — p.__
- [ ] Thermal resistances and the test board they were measured on — p.__
- [ ] Derating curves (current/power versus temperature) — p.__

## Mechanical and layout

- [ ] Package dimensions and tolerances, height — p.__
- [ ] Recommended land pattern and solder-paste notes — p.__
- [ ] Layout recommendations (loop areas, keep-outs, antenna clearance, ground) — p.__
- [ ] Moisture sensitivity / reflow profile limits — p.__

## Warnings and errata

- [ ] Manufacturer warnings, limitations and footnotes in tables — p.__
- [ ] Errata sheet checked (date) — ______
- [ ] Application notes referenced by the datasheet read — list: ______

## Traceability

Every design decision taken from this review goes into one of:
the component record (`components/approved-parts/*.json`: ratings with
`source` page), a schematic note next to the circuit, `docs/requirements.md`
(assumptions), or a calculation file in `hardware/simulations/` marked as an
estimate.

Reviewed by: ________  Date: ________
