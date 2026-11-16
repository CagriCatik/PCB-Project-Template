"""Declared operating states and interfaces, cross-checked against pinmap/BSP.

No arbitrary firmware evaluation or net extraction from drawing coordinates.
Optional native evidence comes only from a current pinned KiCad snapshot.
"""
import csv
import hashlib
import json
from pathlib import Path

from tools.core.common import KitError, VERSION, now, sha256
from tools.core.evidence import recorded_run
from tools.project.assumptions import Assumptions

REQUIRED_STATES = {'battery_only', 'usb_only', 'battery_and_usb', 'off', 'module_absent',
                   'reset', 'bootloader', 'brownout', 'battery_reconnect'}
SAFE_STATES = {'module_absent', 'reset', 'bootloader', 'brownout', 'battery_reconnect', 'off'}
LEVELS = {'low', 'high', 'high_impedance', 'off', 'disabled', 'input'}
PIN_FIELDS = ('reference', 'pin_number', 'schematic_net', 'mcu_port', 'mcu_pin',
              'firmware_signal', 'direction', 'voltage_domain', 'boot_state')
BIND_FIELDS = ('mcu_port', 'mcu_pin', 'direction', 'boot_state', 'active_level', 'inverted', 'safe_state')


def _load(path):
    raw = path.read_bytes()
    data = json.loads(raw)
    if not isinstance(data, dict) or data.get('schema') != 1:
        raise KitError('Expected schema 1 object: ' + str(path))
    return data, hashlib.sha256(raw).hexdigest()


def _rows(config, key):
    value = config.get(key)
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        raise KitError(key + ' must be an array of objects')
    return value


def _ids(rows, label):
    result = {}
    for row in rows:
        key = row.get('id')
        if not isinstance(key, str) or not key.strip() or key in result:
            raise KitError(label + ' needs unique nonempty ids')
        result[key] = row
    return result


def _native(root, path):
    data, digest = _load(Path(path))
    if data.get('kicad') != VERSION or data.get('version_status') != 'TESTED':
        raise KitError('Native contract checks require KiCad %s evidence' % VERSION, 11)
    if not isinstance(data.get('sources'), dict) or not data['sources'] or not isinstance(data.get('electrical'), dict):
        raise KitError('Incomplete schematic snapshot')
    for name, digest in data['sources'].items():
        source = (root / name).resolve()
        if not source.is_relative_to(root) or not source.is_file() or sha256(source) != digest:
            raise KitError('Schematic snapshot is stale or outside project: ' + name)
    nets = data['electrical'].get('nets')
    if not isinstance(nets, list):
        raise KitError('Schematic snapshot has no net array')
    if not any(name.endswith('.kicad_sch') for name in data['sources']):
        raise KitError('Snapshot does not bind a schematic source')
    return {'nets': nets, 'sources': data['sources'], 'digest': digest}


def _check(project, snapshot=None):
    root = Path(project).resolve()
    folder = root / 'hardware/interfaces'
    path = folder / 'design-contracts.json'
    config, config_hash = _load(path)
    bindings_path = root / 'firmware/bsp/pin-bindings.json'
    bindings_config, bindings_hash = _load(bindings_path)
    bindings = _ids(_rows(bindings_config, 'bindings'), 'Firmware bindings')
    assumptions = Assumptions(root)
    pinmap = folder / 'pinmap.csv'
    pinmap_hash = sha256(pinmap)
    with pinmap.open(newline='', encoding='utf-8-sig') as fp:
        reader = csv.DictReader(fp)
        if not reader.fieldnames or len(reader.fieldnames) != len(set(reader.fieldnames)) or not set(PIN_FIELDS).issubset(reader.fieldnames):
            raise KitError('Pinmap needs unique columns including ' + ', '.join(PIN_FIELDS))
        pin_rows = list(reader)
    if any(None in row or any(v is None for v in row.values()) for row in pin_rows):
        raise KitError('Malformed pinmap CSV field count')
    pin_rows = [{k: v.strip() for k, v in row.items()} for row in pin_rows]
    rails = _ids(_rows(config, 'rails'), 'Rails')
    signals = _ids(_rows(config, 'signals'), 'Signals')
    connectors = _ids(_rows(config, 'connectors'), 'Connectors')
    states = _ids(_rows(config, 'states'), 'States')
    native = _native(root, snapshot) if snapshot else None
    nets = native['nets'] if native else None
    findings = []
    def issue(location, message):
        findings.append({'location': location, 'problem': message})
    def text(item, fields, location):
        for key in fields:
            if not isinstance(item.get(key), str) or not item[key].strip():
                issue(location, 'Missing text: ' + key)
    def native_pin(reference, pin, net, location):
        if nets is not None and not any(n.get('name') == net and any(
                m.get('ref') == reference and m.get('pin') == pin for m in n.get('members', [])) for n in nets):
            issue(location, 'Pin/net does not match supplied native snapshot')
    for key, data in [('rails', rails), ('signals', signals), ('connectors', connectors)]:
        if not data and not config.get(key + '_not_applicable_reason'):
            issue(key, 'Empty section requires an explicit not-applicable reason')
    for key, rail in rails.items():
        text(rail, ('source', 'source_reference', 'unpowered_behavior'), 'rail/' + key)
        assumptions.get(rail.get('load_budget'), 'A')
    fw_names, physical, mcu_pins = set(), set(), set()
    for key, signal in signals.items():
        location = 'signal/' + key
        if any(not isinstance(signal.get(field, ''), str) for field in PIN_FIELDS + ('active_level', 'safe_state')):
            raise KitError(location + ' requires string-valued pin fields')
        text(signal, PIN_FIELDS + ('active_level', 'safe_state', 'source_reference'), location)
        if signal.get('direction') not in ('input', 'output', 'bidirectional'):
            issue(location, 'Direction must be input, output or bidirectional')
        if signal.get('active_level') not in {'high', 'low', 'not_applicable'}:
            issue(location, 'Unknown active level')
        if signal.get('boot_state') not in LEVELS or signal.get('safe_state') not in LEVELS:
            issue(location, 'Unknown boot/safe state')
        for field in ('inverted', 'safety_critical'):
            if type(signal.get(field)) is not bool:
                issue(location, field + ' must be boolean')
        if signal.get('voltage_domain') not in rails:
            issue(location, 'Undeclared voltage domain')
        fw = signal.get('firmware_signal')
        physical_key = (signal.get('reference'), signal.get('pin_number'))
        mcu_key = (signal.get('mcu_port'), signal.get('mcu_pin'))
        if fw in fw_names or physical_key in physical or mcu_key in mcu_pins:
            issue(location, 'Duplicate firmware signal, socket pad or MCU pin')
        fw_names.add(fw)
        physical.add(physical_key)
        mcu_pins.add(mcu_key)
        matches = [r for r in pin_rows if r.get('firmware_signal') == fw]
        if len(matches) != 1:
            issue(location, 'Expected exactly one pinmap row for ' + str(fw))
        else:
            for field in PIN_FIELDS:
                if matches[0][field] != signal.get(field):
                    issue(location, 'Pinmap mismatch: ' + field)
            if not matches[0].get('source_reference') or matches[0].get('verification') not in {'documented', 'measured'}:
                issue(location, 'Pinmap provenance is incomplete')
        binding = bindings.get(fw)
        if binding is None:
            issue(location, 'Missing firmware binding')
        else:
            for field in BIND_FIELDS:
                if binding.get(field) != signal.get(field):
                    issue(location, 'Firmware binding mismatch: ' + field)
            text(binding, ('source_reference',), 'binding/' + str(fw))
        native_pin(signal.get('reference'), signal.get('pin_number'), signal.get('schematic_net'), location)
    for fw in set(bindings) - fw_names:
        issue('binding/' + fw, 'Binding has no signal contract')
    for row in pin_rows:
        if row.get('firmware_signal') and row['firmware_signal'] not in fw_names:
            issue('pinmap/' + row['firmware_signal'], 'Application signal has no contract')
    for key, connector in connectors.items():
        location = 'connector/' + key
        text(connector, ('reference', 'view', 'pin1_mark', 'mating_part', 'source_reference'), location)
        count = connector.get('pad_count')
        if type(count) is not int or count < 1:
            raise KitError(location + ' needs positive pad_count (numbered 1..N)')
        pins = _rows(connector, 'pins')
        seen = set()
        for pin in pins:
            number = pin.get('number')
            if not isinstance(number, str) or number in seen or number not in {str(n) for n in range(1, count + 1)}:
                issue(location, 'Duplicate or undeclared pin number')
                continue
            seen.add(number)
            text(pin, ('net', 'voltage_domain', 'unpowered_behavior', 'source_reference'), location)
            if pin.get('direction') not in ('input', 'output', 'bidirectional', 'power', 'ground'):
                issue(location, 'Unknown connector pin direction')
            if pin.get('voltage_domain') not in rails and pin.get('voltage_domain') != 'GND':
                issue(location, 'Undeclared connector voltage domain')
            low = assumptions.get(pin.get('voltage_min'), 'V')
            high = assumptions.get(pin.get('voltage_max'), 'V')
            continuous = assumptions.get(pin.get('current_continuous'), 'A')
            peak = assumptions.get(pin.get('current_peak'), 'A')
            if low > high or continuous > peak:
                issue(location, 'Inverted voltage limits or continuous/peak current limits')
            native_pin(connector.get('reference'), number, pin.get('net'), location)
        if seen != {str(n) for n in range(1, count + 1)}:
            issue(location, 'Not every physical connector pin is documented')
    for key in REQUIRED_STATES - set(states):
        issue('state/' + key, 'Required supply/reset state missing')
    for key, state in states.items():
        location = 'state/' + key
        if type(state.get('applicable')) is not bool:
            issue(location, 'applicable must be boolean')
            continue
        if not state['applicable']:
            text(state, ('reason',), location)
            continue
        text(state, ('entry_condition', 'backfeed_review', 'reason'), location)
        if not isinstance(state.get('rails'), dict) or not isinstance(state.get('signals'), dict):
            raise KitError(location + ' needs rails/signals objects')
        if set(state['rails']) != set(rails) or any(not isinstance(v, str) or v not in {'on', 'off'} for v in state['rails'].values()):
            issue(location, 'Every declared rail needs a known on/off state')
        if set(state['signals']) - set(signals) or any(not isinstance(v, str) or v not in LEVELS for v in state['signals'].values()):
            issue(location, 'Unknown signal or signal state')
        if state.get('rearm') not in ('required', 'not_required', 'not_applicable'):
            issue(location, 'Unknown rearm policy')
        for name, signal in signals.items():
            if signal.get('safety_critical') and signal.get('direction') in {'output', 'bidirectional'}:
                if name not in state['signals']:
                    issue(location, 'Safety output not documented: ' + name)
                elif key in SAFE_STATES and state['signals'][name] != signal.get('safe_state'):
                    issue(location, 'Safety output not in declared safe state: ' + name)
                if key == 'battery_reconnect' and state.get('rearm') != 'required':
                    issue(location, 'Battery reconnect requires deliberate rearm for safety outputs')
    if native and (_native(root, snapshot) != native):
        raise KitError('Native evidence changed during contract check')
    assumptions.unchanged()
    for source, digest in [(path, config_hash), (bindings_path, bindings_hash), (pinmap, pinmap_hash)]:
        if sha256(source) != digest:
            raise KitError('Contract inputs changed during check; discard the run')
    result = {'schema': 1, 'created': now(), 'status': 'FAIL' if findings else 'PASS', 'findings': findings,
              'scope': 'declared contract consistency; not actual arbitrary firmware behaviour or electrical approval',
              'native_connectivity': 'CHECKED' if snapshot else 'NOT_CHECKED',
              'native_snapshot_sha256': native['digest'] if native else None,
              'firmware_evidence': 'reviewed BSP binding declaration; source code not automatically parsed',
              'sources': {str(p.relative_to(root)): d for p, d in [(path, config_hash), (bindings_path, bindings_hash), (pinmap, pinmap_hash)]},
              'basis': assumptions.basis()}
    return result


def check(project, snapshot=None):
    return recorded_run(project, 'contracts', lambda: _check(project, snapshot))
