"""Carrier pin-inventory consistency checks, not physical/electrical approval."""
import csv
import json
from pathlib import Path
import re

from tools.core.common import KitError

ROLES = {"assigned", "reserved", "blocked", "power", "ground", "reset", "boot"}
COLUMNS = {"socket_reference", "socket_pad", "module_header", "module_pin", "gpio",
           "schematic_net", "role", "restrictions", "verification", "source_reference"}


def check(project):
    folder = Path(project).resolve() / "hardware/interfaces"
    config = json.loads((folder / "carrier.json").read_text())
    if not isinstance(config, dict) or config.get("schema") != 1:
        raise KitError("Unsupported carrier.json schema")
    findings = []
    def problem(message, row=None):
        findings.append({"problem": message, **({"row": row} if row else {})})
    module = config.get('module')
    if not isinstance(module, dict):
        raise KitError('carrier.json needs a module object')
    for key in ('manufacturer', 'model', 'revision', 'variant', 'pinout_source'):
        if not isinstance(module.get(key), str) or not module[key].strip():
            problem('Module identity/source missing: ' + key)
    sockets = config.get('sockets')
    if not isinstance(sockets, list):
        raise KitError('carrier.json needs a sockets array')
    expected = set()
    references = set()
    for socket in sockets:
        if not isinstance(socket, dict):
            raise KitError('Each socket needs reference and pad_count')
        ref, count = socket.get('reference'), socket.get('pad_count')
        if not isinstance(ref, str) or not ref or ref in references or type(count) is not int or count < 1:
            raise KitError('Socket reference must be unique and pad_count positive')
        references.add(ref)
        expected.update((ref, str(pad)) for pad in range(1, count + 1))
    if not expected:
        problem('No socket pad inventory declared')
    name = config.get('pin_inventory')
    if not isinstance(name, str) or Path(name).name != name or not name:
        raise KitError('pin_inventory must be a filename in hardware/interfaces')
    with (folder / name).open(newline='') as fp:
        reader = csv.DictReader(fp)
        if not reader.fieldnames or set(reader.fieldnames) != COLUMNS or len(reader.fieldnames) != len(COLUMNS):
            raise KitError('Carrier CSV columns do not match the documented contract')
        rows = list(reader)
    seen, gpios, module_pins = set(), set(), set()
    for number, row in enumerate(rows, 2):
        if None in row or any(value is None for value in row.values()):
            problem('Malformed CSV field count', number)
            continue
        row = {k: v.strip() for k, v in row.items()}
        pin = (row['socket_reference'], row['socket_pad'])
        if pin in seen:
            problem('Duplicate socket pad: %s/%s' % pin, number)
        if pin not in expected:
            problem('Undeclared socket pad: %s/%s' % pin, number)
        seen.add(pin)
        location = (row['module_header'], row['module_pin'])
        if not all(location) or location in module_pins:
            problem('Missing or duplicate physical module pin', number)
        module_pins.add(location)
        if row['role'] not in ROLES:
            problem('Unknown pin role', number)
        if row['role'] in {'reserved', 'blocked'} and not row['restrictions']:
            problem('Reserved/blocked pin needs a reason', number)
        if row['role'] in {'assigned', 'power', 'ground', 'reset', 'boot'} and not row['schematic_net']:
            problem('Connected pin needs a schematic net', number)
        if row['role'] == 'blocked' and row['schematic_net']:
            problem('Blocked pin must not be assigned a carrier net', number)
        if row['role'] in {'power', 'ground'} and row['gpio']:
            problem('Power/ground rows must not claim a GPIO', number)
        if row['gpio']:
            if not re.fullmatch(r'GPIO\d+', row['gpio']) or row['gpio'] in gpios:
                problem('Invalid or duplicate GPIO assignment', number)
            gpios.add(row['gpio'])
        if row['role'] == 'assigned' and not row['gpio']:
            problem('Assigned GPIO row needs a GPIO identifier', number)
        if row['verification'] not in {'documented', 'measured'} or not row['source_reference']:
            problem('Pin needs documented/measured provenance and a source reference', number)
    for ref, pad in sorted(expected - seen):
        problem('Missing socket pad: %s/%s' % (ref, pad))
    return {'status': 'FAIL' if findings else 'PASS', 'scope': 'inventory consistency only; no pinout, geometry or electrical approval',
            'declared_pads': len(expected), 'rows': len(rows), 'findings': findings}
