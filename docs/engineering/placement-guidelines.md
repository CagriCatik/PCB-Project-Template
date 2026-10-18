# PCB placement guidelines

Placement decides most of a board's electrical, thermal and assembly quality;
routing can only connect what placement allows. **Datasheet layout
recommendations and real electrical constraints take precedence over every
heuristic below.** No universal distance limit is given here on purpose: the
right distance comes from the specific parts, currents and frequencies.

## Order of work

1. **Mechanically constrained parts first:** board outline, mounting holes,
   connectors at enclosure openings, switches, LEDs behind light pipes,
   displays, antennas. Confirm against the mechanical drawing or enclosure model
   (`hardware/mechanical/`), including connector mating direction and pin 1.
2. **Keep-outs:** antenna and RF keep-outs exactly as the module or chip
   datasheet specifies (often: no copper on any layer, board edge positioning);
   mounting-hole clearances; height restrictions.
3. **Connectors by accessibility:** where cables arrive, with room for the mating
   plug, latch and fingers; strain relief where needed.
4. **Functional groups:** place each circuit block (power stage, MCU, each
   interface) as a cluster, near the connector or part it serves.
5. **Critical loops and decoupling:** within each group, place the parts that
   form high-current or fast loops first (switching regulator input capacitor,
   switch, diode/inductor; decoupling capacitor to its supply pin and its ground
   return). The goal is the smallest *loop area* including the return path
   through vias or the ground plane, not merely the shortest distance to the pin.
6. **Sensitive versus noisy:** keep analog front-ends, references and crystals
   away from switching nodes, high di/dt loops and heat sources, as their
   datasheets advise. Separation by placement beats separation by later
   copper tricks.
7. **Heat:** spread dissipating parts, give them the copper the datasheet asks
   for, keep heat away from temperature-sensitive parts (references, crystals,
   electrolytic capacitors, sensors). `scripts/kit thermal analyze` gives an
   *estimate* to compare alternatives, not a qualification.
8. **Orientation and assembly:** consistent orientation of polarized parts where
   practical, polarity and pin-1 marks visible after assembly, parts not hidden
   under taller parts, fiducials if the assembler requires them, space for
   rework and test-probe access to test points.

## Placement with routing in mind

Before committing, check routability: are nets that must be short actually
short? Are there channels for buses and for return currents? Will a ground or
reference plane stay unbroken under fast signals? A placement that cannot be
routed without cutting the reference plane is not finished.

Evaluate at least two placement alternatives for non-trivial boards and record
why one was chosen (`docs/decisions/`). Cheap to do now, expensive after routing.

## Verification

- Mechanical: board outline and holes against the enclosure; 3D view with real
  vendor models (`models_3d` gate reports missing ones — never substitute dummy
  geometry and call it the vendor model).
- Courtyard overlaps and silk/pad issues: DRC.
- Antenna/keep-out zones present as rule areas so DRC enforces them.
