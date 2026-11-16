"""Carrier inventory constraints and ESP32 scaffold, using synthetic pin evidence."""
import csv
import json
import shutil
from unittest.mock import patch

from kit_test_support import TempDirTest
from tools.core.common import KitError
from tools.project.carrier import check, COLUMNS
from tools.project.templates import create
from tools.quality import firmware


class CarrierTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.project, _ = create('esp32-carrier', self.tmp / 'ESP32 carrier', 'ESP32', register=False)
        self.folder = self.project / 'hardware/interfaces'

    def valid_inventory(self):
        # Synthetic tooling case, not a DevKit pinout.
        config = {'schema': 1, 'module': {'manufacturer': 'Tooling fixture', 'model': 'Synthetic',
                  'revision': 'test', 'variant': 'test', 'pinout_source': 'fixture only'},
                  'sockets': [{'reference': 'J1', 'pad_count': 3}], 'pin_inventory': 'carrier-pins.csv'}
        rows = []
        for pad, role, gpio, net in [('1', 'assigned', 'GPIO4', 'SIGNAL'), ('2', 'power', '', '+3V3'),
                                      ('3', 'ground', '', 'GND')]:
            rows.append(dict(socket_reference='J1', socket_pad=pad, module_header='J1', module_pin=pad,
                             gpio=gpio, schematic_net=net, role=role, restrictions='',
                             verification='documented', source_reference='synthetic fixture'))
        self.save(config, rows)
        return config, rows

    def save(self, config, rows):
        (self.folder / 'carrier.json').write_text(json.dumps(config))
        with (self.folder / 'carrier-pins.csv').open('w', newline='') as fp:
            writer = csv.DictWriter(fp, fieldnames=sorted(COLUMNS))
            writer.writeheader()
            writer.writerows(rows)

    def test_blank_carrier_is_honestly_incomplete(self):
        result = check(self.project)
        self.assertEqual(result['status'], 'FAIL')
        self.assertEqual(result['declared_pads'], 0)
        self.assertTrue((self.project / 'docs/esp32-carrier.md').is_file())
        self.assertTrue((self.project / 'docs/engineering/carrier-guidelines.md').is_file())
        self.assertIn('BSP_STATUS_GPIO (-1)', (self.project / 'firmware/bsp/esp32/board_pins.h').read_text())
        self.assertIn('espressif32@8.0.0', (self.project / 'firmware/platformio.ini').read_text())
        self.assertEqual(json.loads((self.project / 'meta/project.json').read_text())['firmware'], 'esp32')

    def test_complete_inventory_includes_power_and_ground(self):
        self.valid_inventory()
        result = check(self.project)
        self.assertEqual(result['status'], 'PASS')
        self.assertEqual(result['rows'], 3)
        self.assertIn('inventory consistency only', result['scope'])

    def test_missing_duplicate_and_undeclared_pads_detected(self):
        config, rows = self.valid_inventory()
        for variant in [rows[:2], [rows[0], rows[0], rows[2]],
                        [rows[0], rows[1], {**rows[2], 'socket_pad': '4'}]]:
            self.save(config, variant)
            self.assertEqual(check(self.project)['status'], 'FAIL')

    def test_reserved_blocked_duplicate_gpio_and_provenance_detected(self):
        config, rows = self.valid_inventory()
        for fields in [{'role': 'reserved'}, {'role': 'blocked', 'restrictions': 'memory'},
                       {'verification': 'open'}, {'source_reference': ''}, {'gpio': '4'}]:
            self.save(config, [{**rows[0], **fields}, *rows[1:]])
            self.assertEqual(check(self.project)['status'], 'FAIL')
        self.save(config, [rows[0], {**rows[1], 'gpio': 'GPIO4'}, rows[2]])
        self.assertEqual(check(self.project)['status'], 'FAIL')
        self.save(config, [{**rows[0], 'role': 'blocked', 'restrictions': 'memory', 'schematic_net': ''}, *rows[1:]])
        self.assertEqual(check(self.project)['status'], 'PASS')

    def test_path_escape_and_duplicate_socket_declarations_rejected(self):
        config, rows = self.valid_inventory()
        config['pin_inventory'] = '../outside.csv'
        self.save(config, rows)
        with self.assertRaises(KitError):
            check(self.project)
        config['pin_inventory'] = 'carrier-pins.csv'
        config['sockets'] *= 2
        self.save(config, rows)
        with self.assertRaises(KitError):
            check(self.project)

    def test_esp32_target_builds_without_uploading(self):
        result = {'argv': ['pio', 'run', '-e', 'esp32'], 'exit_code': 0, 'stdout': '', 'stderr': ''}
        with patch.object(firmware.shutil, 'which', return_value='/fake/pio'), patch.object(firmware, 'run', return_value=result) as runner:
            report = firmware.build(self.project, 'esp32')
        self.assertEqual(report['status'], 'PASS')
        self.assertEqual(runner.call_args.args[0], ['pio', 'run', '-e', 'esp32'])
        self.assertNotIn('upload', runner.call_args.args[0])

    def test_missing_platformio_is_not_a_success(self):
        with patch.object(firmware.shutil, 'which', return_value=None), self.assertRaises(KitError):
            firmware.build(self.project, 'esp32')
        report = json.loads((self.project / 'qa/generated/firmware/esp32.json').read_text())
        self.assertEqual(report['status'], 'MISSING_TOOLCHAIN')

    def test_host_application_build(self):
        if not all(shutil.which(t) for t in ('cmake', 'ctest', 'cc')):
            self.skipTest('Host build tools missing')
        self.assertEqual(firmware.build(self.project, 'host')['status'], 'PASS')
