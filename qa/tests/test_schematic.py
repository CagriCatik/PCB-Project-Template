"""Read-only schematic workflow contracts, isolated from user/editor state."""
import copy
import json
from pathlib import Path
import struct
from unittest.mock import patch

from kit_test_support import TempDirTest, requires_kicad
from tools.core.common import KitError
from tools.schematic import evidence, layout, model

XML = '''<export><components><comp ref="R1"><value>10k</value><sheetpath names="/" tstamps="/root/"/><tstamps>r1</tstamps></comp></components>
<nets><net code="1" name="SIGNAL"><node ref="R1" pin="1"/></net><net code="2" name="Net-(R1-Pad2)"><node ref="R1" pin="2"/></net></nets></export>'''
SCH = '''(kicad_sch (uuid root) (paper "A4") (lib_symbols)
(symbol (lib_id "Device:R") (at 30 30 90) (mirror x) (uuid r1)
(property "Reference" "R1" (at 35 30 0) (effects (font (size 1 1))))
(property "Value" "10k" (at 35 32 0) (effects (font (size 1 1))))
(property "Footprint" "Resistor" (at 35 30 0) (effects (font (size 1 1)) (hide yes)))
(in_bom yes) (on_board yes) (dnp no) (pin "1" (uuid pin1))
(instances (project "board" (path "/root" (reference "R1") (unit 1)))))
(label "SIGNAL" (at 20 20 0) (uuid label))
(text "Input conditioning" (at 40 20 0)))'''


def record():
    return {"argv": ["fake-cli"], "exit_code": 0, "stdout": "", "stderr": ""}


def png(path, width, height):
    Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + struct.pack('>I', 13) + b'IHDR' + struct.pack('>II', width, height))


class FakeCLI:
    version = "10.0.7"
    version_status = "TESTED"

    def command(self, command, args):
        output = Path(args[args.index("--output") + 1])
        output.write_text(XML if command[-1] == "netlist" else "%PDF-tooling-test")
        return record()

    def erc(self, schematic, output):
        data = {"sheets": [{"path": "/", "violations": []}]}
        Path(output).write_text(json.dumps(data))
        return record(), data


class SchematicTests(TempDirTest):
    def setUp(self):
        super().setUp()
        self.sch = self.tmp / 'board.kicad_sch'
        self.sch.write_text(SCH)

    def snap(self, name='snapshot.json', cli=None):
        return evidence.snapshot(self.sch, self.tmp / name, cli or FakeCLI())

    def test_layout_rotation_mirror_and_field_moves_do_not_change_snapshot(self):
        a = self.snap()
        self.sch.write_text(SCH.replace('(at 30 30 90) (mirror x)', '(at 80 80 270) (mirror y)')
                            .replace('(at 35 30 0)', '(at 90 90 0)'))
        b = self.snap('after.json')
        self.assertTrue(model.compare(a, b)['identical'])
        self.assertNotEqual(a['sources'], b['sources'])

    def test_connection_value_flags_identity_and_interface_changes_are_detected(self):
        a = self.snap()
        for section, key, value in [('native', 'root', 'other'), ('electrical', 'nets', []),
                                    ('electrical', 'components', [])]:
            b = copy.deepcopy(a)
            b[section][key] = value
            self.assertFalse(model.compare(a, b)['identical'])
        for old, new in [('10k', '20k'), ('dnp no', 'dnp yes'), ('uuid pin1', 'uuid pin2'),
                         ('label "SIGNAL"', 'label "RENAMED"')]:
            self.sch.write_text(SCH.replace(old, new))
            b = self.snap(new.replace(' ', '-') + '.json')
            self.assertFalse(model.compare(a, b)['identical'])

    def test_net_codes_order_and_generated_names_are_not_connectivity(self):
        a = self.tmp / 'a.xml'
        b = self.tmp / 'b.xml'
        a.write_text(XML)
        b.write_text(XML.replace('code="1"', 'code="99"').replace('Net-(R1-Pad2)', 'Net-(Other)'))
        self.assertEqual(model.netlist(a), model.netlist(b))
        b.write_text(XML.replace('pin="1"', 'pin="3"'))
        self.assertNotEqual(model.netlist(a), model.netlist(b))

    def test_repeated_sheets_multiunit_and_cycle(self):
        child = self.tmp / 'child.kicad_sch'
        child.write_text(SCH.replace('uuid root', 'uuid child'))
        self.sch.write_text('(kicad_sch (uuid root) (sheet (uuid s1) (property "Sheetfile" "child.kicad_sch"))'
                            '(sheet (uuid s2) (property "Sheetfile" "child.kicad_sch")))')
        data, hashes = model.inventory(self.sch)
        self.assertEqual(len(data['sheets']), 2)
        self.assertEqual(len(next(s for s in data['sheets'] if s['file'] == self.sch.name)['sheets']), 2)
        child.write_text(SCH.replace('(label "SIGNAL"', '(symbol (uuid r2) (property "Reference" "R1")) (label "SIGNAL"'))
        data, _ = model.inventory(self.sch)
        self.assertEqual(len(next(s for s in data['sheets'] if s['file'] == child.name)['symbols']), 2)
        child.write_text('(kicad_sch (sheet (property "Sheetfile" "board.kicad_sch")))')
        with self.assertRaisesRegex(KitError, 'Cyclic'):
            model.inventory(self.sch)

    def test_lock_existing_output_external_sheet_and_bad_xml_refused(self):
        self.snap()
        with self.assertRaises(KitError):
            self.snap()
        (self.tmp / '~board.kicad_sch.lck').touch()
        with self.assertRaises(KitError):
            self.snap('locked.json')
        self.sch.write_text('(kicad_sch (sheet (property "Sheetfile" "../outside.kicad_sch")))')
        with self.assertRaisesRegex(KitError, 'External'):
            model.inventory(self.sch)
        xml = self.tmp / 'bad.xml'
        xml.write_text('<export/>')
        with self.assertRaises(KitError):
            model.netlist(xml)

    def test_mid_export_source_change_refused(self):
        class EditingCLI(FakeCLI):
            def command(inner, command, args):
                result = super().command(command, args)
                self.sch.write_text(SCH.replace('10k', '20k'))
                return result
        with self.assertRaisesRegex(KitError, 'changed'):
            self.snap(cli=EditingCLI())
        self.assertFalse((self.tmp / 'snapshot.json').exists())

    def fake_raster(self, args, **kwargs):
        if '-singlefile' in args:
            png(str(args[-1]) + '.png', int(args[args.index('-W') + 1]), int(args[args.index('-H') + 1]))
        elif '-png' in args:
            png(str(args[-1]) + '-1.png', 1754, 1240)
        return record()

    def test_review_has_fresh_outputs_hashes_and_never_auto_visual_pass(self):
        config = self.tmp / 'views.json'
        config.write_text(json.dumps({'views': [{'id': 'power', 'page': 1, 'box_mm': [10, 10, 50, 30]}]}))
        with patch.object(evidence, 'run', side_effect=self.fake_raster):
            a = evidence.review(self.sch, self.tmp / 'reviews', config, cli=FakeCLI(), rasterizer='fake')
            b = evidence.review(self.sch, self.tmp / 'reviews', config, cli=FakeCLI(), rasterizer='fake')
        self.assertNotEqual(a['directory'], b['directory'])
        self.assertEqual(a['visual_status'], 'NOT_REVIEWED')
        self.assertEqual(a['status'], 'EVIDENCE_READY')
        self.assertIn('detail-power.png', a['artifacts'])
        self.assertEqual(self.sch.read_text(), SCH)

    def test_evidence_status_detects_later_edits_and_tampered_artifacts(self):
        with patch.object(evidence, 'run', side_effect=self.fake_raster):
            result = evidence.review(self.sch, self.tmp / 'reviews', cli=FakeCLI(), rasterizer='fake')
        manifest = Path(result['directory']) / 'manifest.json'
        self.assertEqual(evidence.status(manifest)['status'], 'CURRENT')
        self.sch.write_text(SCH.replace('10k', '20k'))
        self.assertEqual(evidence.status(manifest)['status'], 'STALE')
        (manifest.parent / 'page-1.png').write_bytes(b'changed')
        self.assertEqual(evidence.status(manifest)['status'], 'MODIFIED')

    def test_failed_export_marks_run_and_cannot_reuse_stale_images(self):
        class BrokenCLI(FakeCLI):
            def command(self, command, args):
                result = super().command(command, args)
                if command[-1] == 'pdf':
                    result['exit_code'] = 1
                return result
        with self.assertRaises(KitError):
            evidence.review(self.sch, self.tmp / 'reviews', cli=BrokenCLI(), rasterizer='fake')
        manifests = list((self.tmp / 'reviews').glob('*/manifest.json'))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text())
        self.assertEqual(manifest['status'], 'FAILED')
        self.assertFalse((manifests[0].parent / 'index.html').exists())

    def test_bad_views_and_out_of_page_crop(self):
        config = self.tmp / 'views.json'
        for view in [{'id': '../bad'}, {'id': 'x', 'page': True, 'box_mm': [0, 0, 1, 1]},
                     {'id': 'x', 'page': 1, 'box_mm': [0, 0, -1, 1]}]:
            config.write_text(json.dumps({'views': [view]}))
            with self.assertRaises(KitError):
                evidence.load_views(config)
        config.write_text(json.dumps({'views': [{'id': 'x', 'page': 1, 'box_mm': [1000, 0, 1, 1]}]}))
        with patch.object(evidence, 'run', side_effect=self.fake_raster), self.assertRaises(KitError):
            evidence.review(self.sch, self.tmp / 'reviews', config, cli=FakeCLI(), rasterizer='fake')

    def test_hints_ignore_hidden_fields_and_notice_multiline_anchor(self):
        self.assertEqual(layout.hints(self.sch)['findings'], [])
        self.sch.write_text(SCH.replace('(at 35 32 0)', '(at 35 30 90)').replace('Input conditioning', 'Line 1\\nLine 2'))
        result = layout.hints(self.sch)
        self.assertEqual(result['status'], 'HINTS_ONLY')
        self.assertEqual(len(result['findings']), 1)
        self.assertEqual(result['findings'][0]['kind'], 'text_anchors_coincide')

    def test_native_evidence_rejects_untested_override(self):
        cli = FakeCLI()
        cli.version = '9.0.2'
        cli.version_status = 'UNTESTED'
        with self.assertRaisesRegex(KitError, 'requires KiCad 10.0.7'):
            self.snap(cli=cli)
        with self.assertRaisesRegex(KitError, 'requires KiCad 10.0.7'):
            evidence.review(self.sch, cli=cli, rasterizer='fake')
        self.assertFalse((self.tmp / 'snapshot.json').exists())

    def test_agent_contract_uses_existing_tools_and_authorizes_scoped_git(self):
        from kit_test_support import ROOT
        for path in [ROOT / 'AGENTS.md', ROOT / 'meta/templates/project-root/AGENTS.md']:
            text = path.read_text()
            self.assertIn('Mandatory toolchain', text)
            self.assertIn('KICAD_KIT_ALLOW_UNTESTED', text)
            self.assertIn('scripts/kit schematic status', text)
            self.assertIn('scripts/kit verify PROJECT', text)
            self.assertIn('commit and push', text)
            self.assertNotIn('owner alone stages', text)
            self.assertNotIn('Only the project owner stages', text)

    def test_toolchain_difference_is_explicit(self):
        a = self.snap()
        b = copy.deepcopy(a)
        b['kicad'] = '9.0.2'
        self.assertFalse(model.compare(a, b)['toolchain_match'])
        self.assertFalse(model.compare(b, b)['toolchain_supported'])

    def test_generated_projects_receive_review_contract(self):
        from tools.project.templates import create
        root, _ = create("generic-pcb", self.tmp / "generated board", "Review", register=False)
        self.assertTrue((root / "docs/engineering/schematic-review.md").is_file())
        self.assertTrue((root / "qa/schematic-views.example.json").is_file())
        self.assertTrue((root / "qa/design-reviews/schematic-review-template.md").is_file())
        self.assertIn("Schematic review", (root / "AGENTS.md").read_text())

    def test_cli_compare_returns_nonzero_for_toolchain_mismatch(self):
        from tools.cli.main import main
        from contextlib import redirect_stdout
        import io
        a = self.snap()
        b = copy.deepcopy(a)
        b['kicad'] = 'other'
        path = self.tmp / 'other.json'
        path.write_text(json.dumps(b))
        with redirect_stdout(io.StringIO()):
            code = main(['schematic', 'compare', str(self.tmp / 'snapshot.json'), str(path)])
        self.assertEqual(code, 20)

    @requires_kicad
    def test_native_fixture_snapshot_and_self_compare(self):
        root = self.fixture_copy()
        data = evidence.snapshot(root / 'divider.kicad_sch', self.tmp / 'native.json')
        self.assertTrue(data['electrical']['components'])
        self.assertTrue(model.compare(data, data)['identical'])
        import shutil
        if shutil.which('pdftoppm'):
            result = evidence.review(root / 'divider.kicad_sch', self.tmp / 'native renders')
            self.assertEqual(result['status'], 'EVIDENCE_READY')
            self.assertTrue(result['artifacts'].get('schematic.pdf'))
