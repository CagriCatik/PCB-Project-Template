# Supply states, interface contracts and static power budgets

Use this workflow before schematic/firmware changes that affect power,
polarity, pin allocation or startup behaviour. It complements native KiCad
checks and physical review. New projects receive **empty, intentionally
incomplete** input files; the tools do not invent component limits or pins.
Run commands from the kit checkout against the target project directory.

## Files and ownership

| Source | Meaning |
| --- | --- |
| `hardware/interfaces/assumptions.json` | Typed numerical inputs with value, provenance, revision, conditions and epistemic status |
| `hardware/interfaces/design-contracts.json` | Rail ownership/budgets, logical signals, connector pins and operating states |
| `hardware/interfaces/pinmap.csv` | Reviewed hardware/firmware interface derived from the schematic |
| `firmware/bsp/pin-bindings.json` | Reviewed declaration of what the actual BSP implements |
| `hardware/simulations/power/budget.json` | Explicit simultaneous-load scenarios referring to the same input register |

The schematic remains the hardware source of truth. Contracts and pinmap are
review artifacts, not independent authorities. Binding declarations do **not**
prove that arbitrary firmware source implements them: review/update the BSP
and declaration together, then use target/interface tests. No automatic C/C++
parser, code generator, safety certification or new release gate is introduced.

```sh
scripts/kit assumptions check /path/to/project
scripts/kit contracts check /path/to/project
scripts/kit power-budget calculate /path/to/project
```

These checks need only Python; they neither edit native files nor require
KiCad. For an actual native pin/net comparison, first close/save KiCad and
capture the root schematic with the mandatory KiCad **10.0.7** toolchain:

```sh
scripts/kit schematic snapshot /path/to/project/Board.kicad_sch --output /path/to/project/qa/generated/current.json
scripts/kit contracts check /path/to/project --snapshot /path/to/project/qa/generated/current.json
```

Only current, source-bound, version-pinned snapshot evidence is accepted.
Pin/net membership must match the **exact exported net name**, including any
hierarchical scope. Without the option, the report says `native_connectivity:
NOT_CHECKED`; it never silently implies a schematic check.

## 1. Source-labelled assumptions

Schema 1 contains an `assumptions` array. Every record has these fields:

```json
{
  "id": "EXAMPLE_BRANCH_R",
  "value": 0.1,
  "unit": "ohm",
  "status": "assumed",
  "source": "Synthetic illustration only; not a measured harness",
  "revision": "example-1",
  "conditions": "Total outgoing and return branch resistance, including contacts"
}
```

Supported units: `V`, `A`, `ohm`, `ratio`, `mm` (lengths such as hole-wall plating for `kit power paths`). Numerical references are case-sensitive
ids; inline numbers are not substituted for references in budgets/contracts.
Every source, revision and conditions field must be explicit. Assumptions may
cite an engineering rationale; do not disguise it as a manufacturer source.

| Status | Interpretation |
| --- | --- |
| guaranteed | A reviewed manufacturer guarantee under the recorded conditions |
| typical | Typical manufacturer data; not a guaranteed limit |
| assumed | Engineering estimate requiring confirmation |
| measured | A measurement for the recorded setup/conditions; not a universal guarantee |

No combination of these statuses turns a calculation into proof. The tool
validates the declarations' completeness, not the truth of their sources.
Reports list the **actually used** inputs and flag non-guaranteed inputs.
Avoid double-counting tolerances or derating: derive a conservative scalar
once, record its derivation in the source/conditions, and reference that id.
Do not use an absolute maximum as the normal operating limit.

## 2. Rails, signals and BSP bindings

`design-contracts.json` has schema 1 and arrays `rails`, `signals`, `connectors`,
`states`. Every item needs a unique nonempty `id`.

Each rail declares `id`, `source`, `source_reference`, `load_budget` (an A input
reference) and `unpowered_behavior`. These describe the intended source and
load allowance; the checker does not prove regulator capability or automatically
sum connector budgets.

Each signal declares these exact pinmap fields as strings:

`reference`, `pin_number`, `schematic_net`, `mcu_port`, `mcu_pin`,
`firmware_signal`, `direction`, `voltage_domain`, `boot_state`.

It additionally needs `active_level`, boolean `inverted`, `safe_state`, boolean
`safety_critical`, and `source_reference`. Use a declared rail id for the voltage
domain. Directions are `input`, `output`, `bidirectional`; active level is
`high`, `low` or `not_applicable`. States are `low`, `high`, `high_impedance`,
`off`, `disabled`, `input`. Describe the actual boundary represented by the net:
MCU output, buffer input and external actuator output may have different states.
Create separate named signals where those boundaries need separate contracts.

Example signal fragment (**synthetic**, not a board allocation):

```json
{
  "id": "ENABLE",
  "reference": "U1", "pin_number": "7", "schematic_net": "ENABLE",
  "mcu_port": "GPIO", "mcu_pin": "7", "firmware_signal": "PIN_ENABLE",
  "direction": "output", "voltage_domain": "VLOGIC", "boot_state": "low",
  "active_level": "high", "inverted": false, "safe_state": "low",
  "safety_critical": true, "source_reference": "Replace with reviewed design evidence"
}
```

The pinmap must have exactly one matching row per firmware signal, including
matching reference/pin/net, port/pin, direction, domain and boot state. Each row
needs `verification` (`documented`/`measured`) and `source_reference`. Duplicate
MCU pins, physical pads, firmware signals and orphan application rows fail.
Shared protocol uses must be represented by one physical signal contract;
this version does not model aliases/multiplexed operating modes on one GPIO.

In `firmware/bsp/pin-bindings.json`, schema 1 has `bindings`, each with `id`
**equal to the firmware_signal** and the fields `mcu_port`, `mcu_pin`,
`direction`, `boot_state`, `active_level`, `inverted`, `safe_state`,
`source_reference`. The checker compares all seven functional fields, including
active polarity and inversion. Changing `*_DIS` to `*_EN` or inverting a buffer
therefore requires coordinated updates. A binding without a signal also fails.

## 3. Physical connector contract

Each connector needs `id`, `reference`, positive `pad_count`, `view`,
`pin1_mark`, `mating_part`, `source_reference`, and a `pins` array. Describe
carrier/module/mating **view direction** explicitly. This first version uses
pads numbered `1..N`; other numbering conventions need an extension.

Every pin needs a string `number`, `net`, `direction`, `voltage_domain`,
`unpowered_behavior`, `source_reference`, plus numerical references
`voltage_min`, `voltage_max` (V), `current_continuous`, `current_peak` (A).
The domain must be a declared rail or `GND`. Directions additionally permit
`power` and `ground`. Use explicit zero-current/zero-voltage inputs where
appropriate, never omitted values. All pads must be present exactly once.

The current numbers are the declared interface allowance/rating under the
recorded conditions. They do not establish contact heating, cable ampacity,
continuous stall permission, protection selectivity or PCB copper capability.
Review source ratings, wire gauge, temperature and mating orientation separately.

A section with no rails/signals/connectors requires a nonempty explanatory
`rails_not_applicable_reason`, `signals_not_applicable_reason` or
`connectors_not_applicable_reason`. This supports genuinely passive designs
without treating a blank MCU interface as complete.

## 4. Supply/reset states and rearm

Account for all of these ids:

`battery_only`, `usb_only`, `battery_and_usb`, `off`, `module_absent`, `reset`,
`bootloader`, `brownout`, `battery_reconnect`.

An applicable state needs boolean `applicable: true`, `entry_condition`,
`backfeed_review`, `reason`, `rearm`, and objects `rails`/`signals`. Each rail
must have a known `on`/`off` state. Each safety-critical output must have an
explicit signal state. `rearm` is `required`, `not_required`, or `not_applicable`.

Reset, bootloader, brownout, module absent, off and battery reconnect must put
safety outputs in their declared safe state. Battery reconnect also requires
`rearm: required` for those outputs: USB-powered logic must not resume stale
enable commands merely because the battery returns. This is a **declared
policy check**; prove the hardware default and firmware transition separately.

Genuinely inapplicable cases use `{ "id": "usb_only", "applicable": false,
"reason": "No USB interface on this design" }`. A reason is mandatory. Review
these exclusions; the checker cannot independently decide their truth.
Include additional project-specific modes, but do not omit the required cases.

## 5. Static rail/common-path/branch calculation

`budget.json` schema 1 has a `scenarios` array. Every scenario has:

- unique `id`, input references `rail_v_min`, `rail_v_max` (V),
  `shared_resistance` (ohm), and a nonempty `loads` array;
- optionally **both** `battery_v_min` (V) and `efficiency_min` (ratio, 0 < eta <= 1)
  for an estimated battery-current figure;
- optionally `rail_current_limit` (A) to compare scenario total current with a
  declared limit. This still does not prove the converter supplies that current.

Each load has a unique `id`, `endpoint`, `branch_resistance` (ohm),
`voltage_min`/`voltage_max` (V), and a `model`:

- `constant_current`: reference `current` (A, >= 0);
- `resistive`: reference `resistance` (ohm, > 0).

The endpoint names where the operating limits apply (e.g. external module
connector). Include the whole relevant supply-and-return resistance **once**.
Put shared PCB/shunt/cable resistance only in the common path. Put each branch's
contacts, adapter and cable resistance only in that branch. Do not compare an
internal motor voltage with a complete servo's terminal-voltage specification
unless the manufacturer's reference point actually justifies it.

For rail voltage V, common resistance Rs, total constant current Ic and
resistive branch conductance G = sum(1/(Rb + Rload)):

```text
Vnode = (V - Rs * Ic) / (1 + Rs * G)
Ibranch = declared current, or Vnode / (Rb + Rload)
Vload = Vnode - Ibranch * Rb
Itotal = sum(Ibranch)
```

Both declared rail corners are calculated. The common drop uses **total
current**; each branch drop uses its **own current**. Per-path I²R losses and
load-voltage margins are reported. The model is limited to positive DC rails,
nonnegative resistances and the two specified load laws. Negative voltages or
non-finite solutions are infeasible, never operating predictions.

For battery estimation the upper-rail-corner source power is divided by
`battery_v_min * efficiency_min`. That figure covers only this rail/scenario,
not the drive motor, ESC, other rails, quiescent current, inrush or regeneration.
Use explicit normal-load, simultaneous-stall and zero-current/no-load scenarios
where relevant. A stall-as-resistance approximation remains an **assumption**;
servo electronics, current limiting and time/temperature behaviour may differ.

This is not an arbitrary tolerance optimiser: use already-derived conservative
inputs and separate scenarios for minimum/maximum path resistance or other
corners. It does not sweep correlations or prove all possible worst cases.
It cannot establish regulator dropout, ripple, transient overshoot, loop
stability, thermal limits, fuse timing or protection performance. Bench tests
remain necessary. Status `WITHIN_LIMITS` means only the declared scenarios fit
the declared limits **under this model**, never a guaranteed design minimum.

## Reports and review

The contracts and budget commands write JSON to ignored
`qa/generated/contracts/run-*/result.json` and
`qa/generated/power-budget/run-*/result.json`.
Reports record input hashes, used assumption records and scope. Each invocation gets a new directory, and failed attempts are
explicitly recorded as `FAILED`; no earlier success is overwritten or reused. No report is a signed release record. Re-run after source changes;
do not use an old report against new inputs. Native sources and native snapshot
hashes are checked again if a contract check uses a snapshot.

Exit 0: declared contracts consistent / assumptions populated / calculated
scenarios within limits. Exit 20: incomplete or conflicting declarations, empty
scenarios or a limit violation. Invalid schema, missing references or unsuitable
units/ranges fail with exit 2; unsupported native evidence exits 11.

Keep the reviewed design discussion in source, including unresolved assumptions
and concrete measurement/closure steps. Do not hide errors by weakening limits,
marking actual modes inapplicable or claiming a typical value is guaranteed.
