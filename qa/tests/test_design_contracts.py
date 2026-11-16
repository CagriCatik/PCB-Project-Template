"""Synthetic tooling inputs; these are not a real circuit or part specifications."""
import copy
import csv
import io
import json
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from kit_test_support import TempDirTest
from tools.core.common import KitError, sha256
from tools.project.assumptions import Assumptions, check as check_assumptions
from tools.project.contracts import check, REQUIRED_STATES
from tools.quality.power_budget import calculate, solve
from tools.project.templates import create


class DesignContractsTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.root, _ = create('generic-pcb', self.tmp / 'Synthetic contract', 'Synthetic', register=False)
        self.folder = self.root / 'hardware/interfaces'
        self.parameters = []
        values = {'RAIL_LOW': (6.8, 'V'), 'RAIL_HIGH': (7, 'V'), 'SHARED': (.1, 'ohm'),
                  'BRANCH': (.1, 'ohm'), 'CURRENT': (2, 'A'), 'MIN': (6, 'V'), 'MAX': (8, 'V'),
                  'BUDGET': (5, 'A'), 'PEAK': (6, 'A'), 'BATTERY': (10, 'V'), 'EFF': (.9, 'ratio')}
        for key, (value, unit) in values.items():
            self.parameters.append({'id': key, 'value': value, 'unit': unit, 'status': 'assumed',
                                    'source': 'synthetic tooling case', 'revision': 'test-1', 'conditions': 'algebra test only'})
        self.save_assumptions()
        self.signal = {'id': 'ENABLE', 'reference': 'U1', 'pin_number': '7', 'schematic_net': 'ENABLE',
                       'mcu_port': 'GPIO', 'mcu_pin': '7', 'firmware_signal': 'PIN_ENABLE',
                       'direction': 'output', 'voltage_domain': 'VLOGIC', 'boot_state': 'low',
                       'active_level': 'high', 'inverted': False, 'safe_state': 'low',
                       'safety_critical': True, 'source_reference': 'synthetic fixture'}
        self.contract = {'schema': 1, 'rails': [{'id': 'VLOGIC', 'source': 'synthetic fixed rail',
                         'source_reference': 'fixture', 'load_budget': 'BUDGET', 'unpowered_behavior': 'off'}],
                         'signals': [self.signal], 'connectors': [{'id': 'OUTPUT', 'reference': 'J1',
                         'pad_count': 1, 'view': 'carrier top view', 'pin1_mark': 'square pad',
                         'mating_part': 'fixture only', 'source_reference': 'fixture',
                         'pins': [{'number': '1', 'net': 'ENABLE', 'direction': 'output', 'voltage_domain': 'VLOGIC',
                         'unpowered_behavior': 'low by declared pull', 'source_reference': 'fixture',
                         'voltage_min': 'MIN', 'voltage_max': 'MAX', 'current_continuous': 'BUDGET', 'current_peak': 'PEAK'}]}],
                         'states': [{'id': state, 'applicable': True, 'entry_condition': 'synthetic entry',
                         'backfeed_review': 'synthetic declaration only', 'reason': 'test',
                         'rails': {'VLOGIC': 'off' if state == 'off' else 'on'}, 'signals': {'ENABLE': 'low'},
                         'rearm': 'required'} for state in sorted(REQUIRED_STATES)]}
        self.save_contract()
        self.bindings = {'schema': 1, 'bindings': [{**self.signal, 'id': 'PIN_ENABLE'}]}
        self.write('firmware/bsp/pin-bindings.json', self.bindings)
        self.write_pinmap()
        self.scenario = {'id': 'simultaneous', 'rail_v_min': 'RAIL_LOW', 'rail_v_max': 'RAIL_HIGH',
                         'shared_resistance': 'SHARED', 'battery_v_min': 'BATTERY', 'efficiency_min': 'EFF',
                         'loads': [{'id': name, 'model': 'constant_current', 'current': 'CURRENT',
                         'branch_resistance': 'BRANCH', 'voltage_min': 'MIN', 'voltage_max': 'MAX',
                         'endpoint': 'synthetic connector'} for name in ['left', 'right']]}
        self.save_budget()

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))
        return path

    def save_assumptions(self):
        self.write('hardware/interfaces/assumptions.json', {'schema': 1, 'assumptions': self.parameters})

    def save_contract(self):
        self.write('hardware/interfaces/design-contracts.json', self.contract)

    def save_budget(self):
        self.write('hardware/simulations/power/budget.json', {'schema': 1, 'scenarios': [self.scenario]})

    def write_pinmap(self, edits=None):
        row = {k: self.signal[k] for k in ('reference', 'pin_number', 'schematic_net', 'mcu_port', 'mcu_pin',
               'firmware_signal', 'direction', 'voltage_domain', 'boot_state')}
        row.update(board_revision='test', verification='documented', source_reference='fixture')
        row.update(edits or {})
        with (self.folder / 'pinmap.csv').open('w', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=list(row))
            writer.writeheader()
            writer.writerow(row)

    def test_complete_declared_contract_and_source_hashes(self):
        result = check(self.root)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['native_connectivity'], 'NOT_CHECKED')
        self.assertIn('not automatically parsed', result['firmware_evidence'])
        self.assertEqual(len(result['sources']), 3)
        self.assertTrue(result['basis']['contains_non_guaranteed_inputs'])

    def test_pinmap_gpio_direction_boot_and_net_drift(self):
        for key in ('mcu_pin', 'direction', 'boot_state', 'schematic_net'):
            self.write_pinmap({key: 'changed'})
            result = check(self.root)
            self.assertEqual(result['status'], 'FAIL')
            self.assertTrue(any('Pinmap mismatch: ' + key == f['problem'] for f in result['findings']))

    def test_firmware_inversion_polarity_and_safe_state_drift(self):
        for field, value in [('inverted', True), ('active_level', 'low'), ('safe_state', 'high')]:
            data = copy.deepcopy(self.bindings)
            data['bindings'][0][field] = value
            self.write('firmware/bsp/pin-bindings.json', data)
            self.assertEqual(check(self.root)['status'], 'FAIL')

    def test_missing_state_unsafe_output_and_automatic_restart_detected(self):
        base = copy.deepcopy(self.contract)
        self.contract['states'] = self.contract['states'][:-1]
        self.save_contract()
        self.assertEqual(check(self.root)['status'], 'FAIL')
        for key, field, value in [('reset', 'signals', {'ENABLE': 'high'}), ('battery_reconnect', 'rearm', 'not_required')]:
            self.contract = copy.deepcopy(base)
            next(s for s in self.contract['states'] if s['id'] == key)[field] = value
            self.save_contract()
            self.assertEqual(check(self.root)['status'], 'FAIL')

    def test_inapplicable_state_requires_reason(self):
        state = self.contract['states'][0]
        state.clear()
        state.update(id='battery_and_usb', applicable=False)
        self.save_contract()
        self.assertEqual(check(self.root)['status'], 'FAIL')
        state['reason'] = 'No USB interface in this synthetic scenario'
        self.save_contract()
        self.assertEqual(check(self.root)['status'], 'PASS')

    def test_connector_incomplete_pinout_limits_and_view(self):
        connector = self.contract['connectors'][0]
        connector['pad_count'] = 2
        self.save_contract()
        self.assertEqual(check(self.root)['status'], 'FAIL')
        connector['pad_count'] = 1
        del connector['view']
        connector['pins'][0]['voltage_min'] = 'MAX'
        connector['pins'][0]['voltage_max'] = 'MIN'
        self.save_contract()
        self.assertEqual(check(self.root)['status'], 'FAIL')

    def snapshot(self):
        sch = self.root / 'Synthetic.kicad_sch'
        return self.write('native.json', {'schema': 1, 'kicad': '10.0.7', 'version_status': 'TESTED',
               'sources': {sch.name: sha256(sch)}, 'electrical': {'nets': [{'name': 'ENABLE',
               'members': [{'ref': 'U1', 'pin': '7'}, {'ref': 'J1', 'pin': '1'}]}]}})

    def test_optional_current_native_net_membership(self):
        path = self.snapshot()
        self.assertEqual(check(self.root, path)['native_connectivity'], 'CHECKED')
        data = json.loads(path.read_text())
        data['electrical']['nets'][0]['members'][0]['pin'] = '8'
        path.write_text(json.dumps(data))
        self.assertEqual(check(self.root, path)['status'], 'FAIL')

    def test_stale_and_unpinned_native_evidence_rejected(self):
        path = self.snapshot()
        data = json.loads(path.read_text())
        data['kicad'] = '9.0.2'
        path.write_text(json.dumps(data))
        with self.assertRaises(KitError):
            check(self.root, path)
        path = self.snapshot()
        (self.root / 'Synthetic.kicad_sch').write_text('changed')
        with self.assertRaisesRegex(KitError, 'stale'):
            check(self.root, path)

    def test_power_shared_total_and_per_branch_current(self):
        loads = [{'id': name, 'model': 'resistive', 'branch_ohm': 1., 'value': 3.} for name in ['left', 'right']]
        result = solve(12., 1., loads)
        self.assertAlmostEqual(result['common_node_v'], 8.)
        self.assertAlmostEqual(result['total_current_a'], 4.)
        self.assertEqual([b['voltage_v'] for b in result['branches']], [6., 6.])
        # Conservation of power at the source, common path, branches and loads.
        self.assertAlmostEqual(result['rail_power_w'], result['shared_loss_w'] +
                               sum(b['branch_loss_w'] + b['voltage_v'] * b['current_a'] for b in result['branches']))

    def test_mixed_load_solution(self):
        result = solve(12., 1., [{'id': 'fixed', 'model': 'constant_current', 'branch_ohm': 0., 'value': 1.},
                                {'id': 'resistor', 'model': 'resistive', 'branch_ohm': 1., 'value': 3.}])
        self.assertAlmostEqual(result['common_node_v'], 8.8)
        self.assertAlmostEqual(result['total_current_a'], 3.2)

    def test_power_limits_and_estimate_provenance(self):
        result = calculate(self.root)
        self.assertEqual(result['status'], 'WITHIN_LIMITS')
        self.assertIn('ESTIMATE', result['label'])
        self.assertAlmostEqual(result['scenarios'][0]['lower_rail_corner']['branches'][0]['voltage_v'], 6.2)
        self.assertAlmostEqual(result['scenarios'][0]['battery_current_estimate_a'], 28 / 9)
        self.parameters[5]['value'] = 6.5
        self.save_assumptions()
        self.assertEqual(calculate(self.root)['status'], 'OUTSIDE_LIMITS')

    def test_no_load_overvoltage_and_impossible_constant_current(self):
        self.parameters[4]['value'] = 0
        self.parameters[6]['value'] = 6.9
        self.save_assumptions()
        self.assertEqual(calculate(self.root)['status'], 'OUTSIDE_LIMITS')
        self.parameters[4]['value'] = 100
        self.save_assumptions()
        result = calculate(self.root)
        self.assertFalse(result['scenarios'][0]['lower_rail_corner']['feasible'])
        self.assertIsNone(result['scenarios'][0]['battery_current_estimate_a'])

    def test_assumptions_duplicate_nonfinite_missing_source_and_wrong_unit(self):
        for field, value in [('value', float('nan')), ('value', True), ('source', ''), ('unit', 'mystery')]:
            params = copy.deepcopy(self.parameters)
            params[0][field] = value
            self.write('hardware/interfaces/assumptions.json', {'schema': 1, 'assumptions': params})
            with self.assertRaises(KitError):
                Assumptions(self.root)
        self.save_assumptions()
        self.scenario['rail_v_min'] = 'CURRENT'
        self.save_budget()
        with self.assertRaisesRegex(KitError, 'expected V'):
            calculate(self.root)
        self.parameters.append(self.parameters[0])
        self.save_assumptions()
        with self.assertRaisesRegex(KitError, 'Duplicate'):
            Assumptions(self.root)

    def test_unresolved_and_out_of_range_parameters(self):
        for key, value in [('rail_v_min', 'MISSING'), ('efficiency_min', 'CURRENT')]:
            scenario = copy.deepcopy(self.scenario)
            scenario[key] = value
            self.write('hardware/simulations/power/budget.json', {'schema': 1, 'scenarios': [scenario]})
            with self.assertRaises(KitError):
                calculate(self.root)
        self.save_budget()
        self.parameters[-1]['value'] = 1.1
        self.save_assumptions()
        with self.assertRaisesRegex(KitError, 'Efficiency'):
            calculate(self.root)
        self.parameters[-1]['value'] = 1e-320
        self.save_assumptions()
        with self.assertRaises(KitError):
            calculate(self.root)

    def test_fresh_template_is_incomplete_without_invented_values(self):
        root, _ = create('esp32-carrier', self.tmp / 'Blank contracts', 'Blank', register=False)
        self.assertEqual(check(root)['status'], 'FAIL')
        self.assertEqual(calculate(root)['status'], 'INCOMPLETE')
        self.assertEqual(check_assumptions(root)['status'], 'INCOMPLETE')
        self.assertTrue((root / 'firmware/bsp/pin-bindings.json').is_file())

    def test_cli_exits_nonzero_on_unsafe_contract(self):
        from tools.cli.main import main
        self.write_pinmap({'boot_state': 'high'})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(main(['contracts', 'check', str(self.root)]), 20)
            self.assertEqual(main(['power-budget', 'calculate', str(self.root)]), 0)

    def test_current_limit_and_resistive_budget_model(self):
        self.scenario['rail_current_limit'] = 'CURRENT'
        self.save_budget()
        self.assertEqual(calculate(self.root)['status'], 'OUTSIDE_LIMITS')
        self.parameters.append({'id': 'RLOAD', 'value': 2., 'unit': 'ohm', 'status': 'assumed',
                                'source': 'fixture', 'revision': 'test', 'conditions': 'resistive load'})
        self.save_assumptions()
        self.scenario.pop('rail_current_limit')
        for load in self.scenario['loads']:
            load.pop('current')
            load.update(model='resistive', resistance='RLOAD')
        self.save_budget()
        self.assertTrue(calculate(self.root)['scenarios'][0]['lower_rail_corner']['feasible'])

    def test_failed_run_cannot_reuse_previous_success(self):
        good = calculate(self.root)
        self.scenario['rail_v_min'] = 'MISSING'
        self.save_budget()
        with self.assertRaises(KitError):
            calculate(self.root)
        folder = self.root / 'qa/generated/power-budget'
        records = [json.loads(p.read_text()) for p in folder.glob('*/result.json')]
        self.assertEqual(len(records), 2)
        self.assertEqual({r['status'] for r in records}, {'WITHIN_LIMITS', 'FAILED'})
        self.assertEqual(json.loads((folder / Path(good['directory']).name / 'result.json').read_text())['status'], 'WITHIN_LIMITS')

    def test_source_drift_rejected(self):
        real = Assumptions.unchanged
        def changed(instance):
            self.parameters[0]['value'] = 7.1
            self.save_assumptions()
            real(instance)
        with patch.object(Assumptions, 'unchanged', changed), self.assertRaisesRegex(KitError, 'changed'):
            calculate(self.root)
