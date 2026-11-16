"""Static rail/branch voltage estimate with one common-current path.

Analytical model: node = (rail - Rshared*sum(Iconstant)) /
(1 + Rshared*sum(1/(Rbranch+Rload))). Resistive loads see their own branch
current, never the total current. No converter, thermal or transient simulation.
"""
import hashlib
import json
import math
from pathlib import Path

from tools.core.common import KitError, now, sha256
from tools.core.evidence import recorded_run
from tools.project.assumptions import Assumptions


def solve(rail_v, shared_ohm, loads):
    constant = sum(l['value'] for l in loads if l['model'] == 'constant_current')
    conductance = sum(1 / (l['branch_ohm'] + l['value']) for l in loads if l['model'] == 'resistive')
    denominator = 1 + shared_ohm * conductance
    if not all(math.isfinite(v) for v in (constant, conductance, denominator)):
        raise KitError('Power estimate overflow; inputs exceed the numeric model range')
    node = (rail_v - shared_ohm * constant) / denominator
    branches = []
    for load in loads:
        current = load['value'] if load['model'] == 'constant_current' else node / (load['branch_ohm'] + load['value'])
        voltage = node - current * load['branch_ohm']
        branches.append({'id': load['id'], 'current_a': current, 'voltage_v': voltage,
                         'branch_loss_w': current * current * load['branch_ohm']})
    total = sum(b['current_a'] for b in branches)
    if not all(math.isfinite(value) for value in [node, total, total * total * shared_ohm, rail_v * total] +
               [v for b in branches for k, v in b.items() if k != 'id']):
        raise KitError('Power estimate overflow; inputs exceed the numeric model range')
    return {'feasible': node >= 0 and all(b['voltage_v'] >= 0 for b in branches),
            'common_node_v': node, 'total_current_a': total,
            'shared_drop_v': total * shared_ohm, 'shared_loss_w': total * total * shared_ohm,
            'rail_power_w': rail_v * total, 'branches': branches}


def _calculate(project):
    root = Path(project).resolve()
    path = root / 'hardware/simulations/power/budget.json'
    raw = path.read_bytes()
    config_hash = hashlib.sha256(raw).hexdigest()
    config = json.loads(raw)
    if not isinstance(config, dict) or config.get('schema') != 1 or not isinstance(config.get('scenarios'), list):
        raise KitError('Expected power budget schema 1 with scenarios array')
    register = Assumptions(root)
    scenarios, ids = [], set()
    for scenario in config['scenarios']:
        if not isinstance(scenario, dict) or not isinstance(scenario.get('id'), str) or not scenario['id'] or scenario['id'] in ids:
            raise KitError('Power scenarios need unique nonempty ids')
        ids.add(scenario['id'])
        get = register.get
        vmin = get(scenario.get('rail_v_min'), 'V', strict=True)
        vmax = get(scenario.get('rail_v_max'), 'V', strict=True)
        if vmin > vmax:
            raise KitError('Rail minimum exceeds maximum: ' + scenario['id'])
        shared = get(scenario.get('shared_resistance'), 'ohm')
        loads, load_ids = [], set()
        if not isinstance(scenario.get('loads'), list) or not scenario['loads']:
            raise KitError('Each scenario needs explicit loads (zero current may model no-load)')
        for load in scenario['loads']:
            if not isinstance(load, dict) or not isinstance(load.get('id'), str) or not load['id'] or load['id'] in load_ids:
                raise KitError('Loads need unique nonempty ids within a scenario')
            load_ids.add(load['id'])
            model = load.get('model')
            if model not in ('constant_current', 'resistive'):
                raise KitError('Load model must be constant_current or resistive')
            value = get(load.get('current') if model == 'constant_current' else load.get('resistance'),
                        'A' if model == 'constant_current' else 'ohm', strict=model == 'resistive')
            required_min = get(load.get('voltage_min'), 'V')
            required_max = get(load.get('voltage_max'), 'V', strict=True)
            if required_min > required_max:
                raise KitError('Consumer minimum exceeds maximum: ' + load['id'])
            if not isinstance(load.get('endpoint'), str) or not load['endpoint'].strip():
                raise KitError('Every load needs the physical voltage endpoint')
            loads.append({'id': load['id'], 'model': model, 'value': value,
                          'branch_ohm': get(load.get('branch_resistance'), 'ohm'),
                          'voltage_min': required_min, 'voltage_max': required_max, 'endpoint': load['endpoint']})
        low, high = solve(vmin, shared, loads), solve(vmax, shared, loads)
        findings = []
        if not low['feasible'] or not high['feasible']:
            findings.append({'problem': 'Constant-current load scenario is physically infeasible in this model'})
        for load, branch_low, branch_high in zip(loads, low['branches'], high['branches']):
            branch_low['minimum_margin_v'] = branch_low['voltage_v'] - load['voltage_min']
            branch_high['maximum_margin_v'] = load['voltage_max'] - branch_high['voltage_v']
            if branch_low['minimum_margin_v'] < 0 or branch_high['maximum_margin_v'] < 0:
                findings.append({'load': load['id'], 'endpoint': load['endpoint'], 'problem': 'Voltage outside declared operating limits'})
        current_limit = scenario.get('rail_current_limit')
        if current_limit is not None:
            limit = get(current_limit, 'A', strict=True)
            if max(low['total_current_a'], high['total_current_a']) > limit:
                findings.append({'problem': 'Rail current exceeds the declared scenario limit'})
        result = {'id': scenario['id'], 'status': 'OUTSIDE_LIMITS' if findings else 'WITHIN_LIMITS',
                  'lower_rail_corner': low, 'upper_rail_corner': high, 'findings': findings}
        battery, efficiency = scenario.get('battery_v_min'), scenario.get('efficiency_min')
        if battery is not None or efficiency is not None:
            vb = get(battery, 'V', strict=True)
            eta = get(efficiency, 'ratio', strict=True)
            if eta > 1:
                raise KitError('Efficiency must be <= 1')
            input_power_factor = vb * eta
            if input_power_factor <= 0 or not math.isfinite(input_power_factor):
                raise KitError('Battery/efficiency inputs exceed the numeric model range')
            current = high['rail_power_w'] / input_power_factor if high['feasible'] else None
            if current is not None and not math.isfinite(current):
                raise KitError('Battery-current estimate overflow')
            result['battery_current_estimate_a'] = current
        scenarios.append(result)
    register.unchanged()
    if sha256(path) != config_hash:
        raise KitError('Power budget changed during calculation; discard the run')
    result = {'schema': 1, 'created': now(), 'status': 'INCOMPLETE' if not scenarios else
              'OUTSIDE_LIMITS' if any(s['findings'] for s in scenarios) else 'WITHIN_LIMITS',
              'label': 'ESTIMATE — not a guaranteed voltage/current capability or hardware approval',
              'scope': 'static declared scenarios only; no thermal, dropout, dynamic stability or transient validation',
              'config_sha256': config_hash, 'basis': register.basis(), 'scenarios': scenarios}
    return result


def calculate(project):
    return recorded_run(project, 'power-budget', lambda: _calculate(project))
