"""Project generation, name/path handling, non-destructive behaviour, native template install."""

import json
import subprocess

from kit_test_support import NATIVE, ROOT, TempDirTest, requires_kicad
from tools.core import kicad_env
from tools.core import sexpr
from tools.project import templates as template_engine
from tools.core.common import KitError

ALL = ("generic-pcb", "stm32-embedded", "arduino-shield")
OFFLINE = ("generic-pcb", "stm32-embedded")  # no KiCad install needed to materialize


class NameTests(TempDirTest):
    def test_invalid_names_rejected(self):
        for name in ["", " lead", "trail ", "dot.", "a/b", "a\\b", 'q"uote', "x" * 81, "-dash", "..", "a..b",
                     "con", "tab\tname", "new\nline", "é-accent"]:
            with self.subTest(name=name), self.assertRaises(KitError):
                template_engine.validate_name(name)

    def test_valid_names_accepted(self):
        for name in ["Board", "My Board v2", "motor_ctl-1.0", "A", "9volt"]:
            self.assertEqual(template_engine.validate_name(name), name)

    def test_invalid_name_leaves_no_files(self):
        with self.assertRaises(KitError):
            template_engine.create("generic-pcb", self.tmp / "bad", "bad/name", register=False)
        self.assertFalse((self.tmp / "bad").exists())

    def test_unknown_template(self):
        with self.assertRaises(KitError):
            template_engine.create("nope", self.tmp / "x", "x", register=False)


class GenerationTests(TempDirTest):
    def create(self, template, name="My Board"):
        path, record = template_engine.create(template, self.tmp / "projects with spaces" / name, name,
                                              register=False)
        return path, record

    def test_offline_templates_generate_complete_layout(self):
        for template in (ALL if NATIVE else OFFLINE):
            with self.subTest(template=template):
                path, record = self.create(template, "Board %s" % template)
                for d in ("hardware", "firmware", "components", "manufacturing", "docs", "qa"):
                    self.assertTrue((path / d).is_dir(), d)
                files = [path / ("Board %s.%s" % (template, e)) for e in ("kicad_pro", "kicad_sch", "kicad_pcb")]
                self.assertTrue(all(f.is_file() for f in files))
                # Native files parse as KiCad S-expressions / JSON with the right roots.
                self.assertEqual(sexpr.head(sexpr.load(files[1])), "kicad_sch")
                self.assertEqual(sexpr.head(sexpr.load(files[2])), "kicad_pcb")
                json.loads(files[0].read_text())
                self.assertEqual(record["template"], template)
                self.assertEqual(json.loads((path / "meta/project.json").read_text())["name"], "Board %s" % template)
                self.assertIn("Board %s" % template, (path / "README.md").read_text())
                self.assertNotIn("{{", (path / "README.md").read_text() + (path / "AGENTS.md").read_text())
                # Kit-only content never leaks into a project.
                for leaked in ("tools", "scripts", "hardware/native-defaults", "firmware/templates", "qa/fixtures",
                               "docs/archive", "docs/project-template", ".venv"):
                    self.assertFalse((path / leaked).exists(), leaked)
                self.assertTrue((path / "qa/verification.json").is_file())
                self.assertTrue((path / ".gitignore").is_file() and (path / ".gitattributes").is_file())

    def test_firmware_overlays_match_template(self):
        generic, _ = self.create("generic-pcb", "G")
        stm32, _ = self.create("stm32-embedded", "S")
        self.assertFalse((generic / "firmware/CMakeLists.txt").exists())
        self.assertTrue((stm32 / "firmware/CMakePresets.json").is_file())
        presets = json.loads((stm32 / "firmware/CMakePresets.json").read_text())
        self.assertEqual({p["name"] for p in presets["configurePresets"]}, {"host-tests", "stm32-debug"})
        self.assertEqual(json.loads((stm32 / "qa/verification.json").read_text())["gates"]["firmware"], "advisory")

    def test_independent_projects_get_distinct_schematic_uuids(self):
        a, _ = self.create("generic-pcb", "A")
        b, _ = self.create("generic-pcb", "B")
        ua = sexpr.value(sexpr.load(a / "A.kicad_sch"), "uuid")
        ub = sexpr.value(sexpr.load(b / "B.kicad_sch"), "uuid")
        self.assertNotEqual(ua, ub)

    def test_existing_destination_never_overwritten(self):
        dest = self.tmp / "taken"
        dest.mkdir()
        (dest / "notes.txt").write_text("keep me")
        with self.assertRaises(KitError) as ctx:
            template_engine.create("generic-pcb", dest, "taken", register=False)
        self.assertEqual(ctx.exception.exit_code, 18)
        self.assertEqual(sorted(p.name for p in dest.iterdir()), ["notes.txt"])
        self.assertEqual((dest / "notes.txt").read_text(), "keep me")

    def test_existing_file_destination_refused(self):
        dest = self.tmp / "file"
        dest.write_text("x")
        with self.assertRaises(KitError):
            template_engine.create("generic-pcb", dest, "file", register=False)
        self.assertEqual(dest.read_text(), "x")

    def test_empty_existing_directory_is_used(self):
        dest = self.tmp / "empty"
        dest.mkdir()
        path, _ = template_engine.create("generic-pcb", dest, "empty", register=False)
        self.assertTrue((path / "empty.kicad_pro").is_file())

    def test_destination_inside_kit_refused(self):
        with self.assertRaises(KitError):
            template_engine.create("generic-pcb", ROOT / "qa/generated/should-not-exist", "x", register=False)
        self.assertFalse((ROOT / "qa/generated/should-not-exist").exists())

    def test_git_option_initializes_without_commit(self):
        path, _ = template_engine.create("generic-pcb", self.tmp / "with git", "with git", git=True, register=False)
        self.assertTrue((path / ".git").is_dir())
        head = subprocess.run(["git", "-C", str(path), "rev-parse", "--verify", "HEAD"], capture_output=True)
        self.assertNotEqual(head.returncode, 0, "project creation must not create commits")

    def test_registration_is_idempotent(self):
        from tools.project import registry

        path, _ = template_engine.create("generic-pcb", self.tmp / "reg", "reg", register=True)
        registry.register_project(path)
        rows = [r for r in registry.list_projects() if r["path"] == str(path.resolve())]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["template"], "generic-pcb")
        registry.forget_project(path)
        self.assertFalse(any(r["path"] == str(path.resolve()) for r in registry.list_projects()))

    @requires_kicad
    def test_arduino_shield_from_official_template(self):
        path, record = self.create("arduino-shield", "Uno Shield")
        base = record["kicad_base"]
        self.assertEqual(base["template"], "Arduino_Uno")
        self.assertIn("Caleb Reister", base["attribution"])
        sch = (path / "Uno Shield.kicad_sch").read_text()
        self.assertNotIn('(project "Arduino_Uno"', sch)
        self.assertIn('(project "Uno Shield"', sch)
        pcb = (path / "Uno Shield.kicad_pcb").read_text()
        self.assertNotIn("KICAD9_3DMODEL_DIR", pcb)
        for m in base["model_migrations"]:
            target = m["to"].replace("${KICAD10_3DMODEL_DIR}", kicad_env.path_vars()["KICAD10_3DMODEL_DIR"])
            self.assertTrue(__import__("os").path.isfile(target), target)
        self.assertIn("hardware/libraries/footprints/Arduino_MountingHole.pretty", (path / "fp-lib-table").read_text())
        self.assertTrue((path / "hardware/libraries/footprints/Arduino_MountingHole.pretty").is_dir())
        self.assertFalse((path / "Arduino_MountingHole.pretty").exists())

    @requires_kicad
    def test_generated_projects_load_in_kicad(self):
        """kicad-cli and pcbnew must load every template's native files."""
        from tools.core.common import run
        from tools.kicad.cli import KiCadCLI

        cli = KiCadCLI()
        for template in ALL:
            with self.subTest(template=template):
                path, _ = self.create(template, "Load %s" % template)
                sch, pcb = path / ("Load %s.kicad_sch" % template), path / ("Load %s.kicad_pcb" % template)
                rec, report = cli.erc(sch, self.tmp / (template + "-erc.json"))
                self.assertIsNotNone(report, rec["stderr"])
                self.assertEqual(report["kicad_version"], kicad_env.KICAD_VERSION)
                load = run([kicad_env.bundled_python(), "-c",
                            "import pcbnew,sys; b=pcbnew.LoadBoard(sys.argv[1]); print(len(b.GetFootprints()))", pcb])
                self.assertEqual(load["exit_code"], 0, load["stderr"][-500:])


class NativeInstallTests(TempDirTest):
    def test_install_is_idempotent_and_preserves_foreign_dirs(self):
        dest = self.tmp / "KiCad templates"
        foreign = dest / "generic-pcb"
        foreign.mkdir(parents=True)
        (foreign / "mine.txt").write_text("user content")
        if not NATIVE:
            self.skipTest("arduino-shield template needs the KiCad bundle")
        first = {r["template"]: r["action"] for r in template_engine.install_native(dest)["results"]}
        self.assertEqual(first["generic-pcb"], "SKIPPED_FOREIGN")
        self.assertEqual(first["stm32-embedded"], "INSTALLED")
        self.assertEqual((foreign / "mine.txt").read_text(), "user content")
        second = {r["template"]: r["action"] for r in template_engine.install_native(dest)["results"]}
        self.assertEqual(second["stm32-embedded"], "UNCHANGED")
        self.assertEqual(second["arduino-shield"], "UNCHANGED")
        # KiCad's template mechanism needs meta/info.html with a title and one .kicad_pro.
        for template in ("stm32-embedded", "arduino-shield"):
            folder = dest / template
            self.assertTrue(template_engine.html_title(folder / "meta/info.html"))
            self.assertEqual([p.name for p in folder.glob("*.kicad_pro")], [template + ".kicad_pro"])
        self.assertTrue((dest / "arduino-shield/meta/brd.png").is_file())
        # KiCad copies text verbatim: the README must not carry the template id as project name.
        readme = (dest / "stm32-embedded/README.md").read_text()
        self.assertTrue(readme.startswith("# New PCB project"))
        self.assertNotIn("stm32-embedded", readme.splitlines()[0])

    @requires_kicad
    def test_locally_modified_template_is_not_replaced(self):
        dest = self.tmp / "tpl"
        template_engine.install_native(dest)
        edited = dest / "stm32-embedded/README.md"
        edited.write_text("my edits")
        result = {r["template"]: r["action"] for r in template_engine.install_native(dest, update=True)["results"]}
        self.assertEqual(result["stm32-embedded"], "SKIPPED_MODIFIED")
        self.assertEqual(edited.read_text(), "my edits")
        states = {r["template"]: r["state"] for r in template_engine.native_status(dest)["templates"]}
        self.assertEqual(states["stm32-embedded"], "MODIFIED")
        self.assertEqual(states["generic-pcb"], "INSTALLED")

    @requires_kicad
    def test_outdated_template_updates_only_with_flag(self):
        dest = self.tmp / "tpl"
        template_engine.install_native(dest)
        marker = dest / "generic-pcb" / template_engine.MARKER
        data = json.loads(marker.read_text())
        data["identity"] = {"changed": "by an older kit"}
        data["kit_version"] = "0.0.1"
        marker.write_text(json.dumps(data))
        actions = {r["template"]: r["action"] for r in template_engine.install_native(dest)["results"]}
        self.assertEqual(actions["generic-pcb"], "UPDATE_AVAILABLE")
        actions = {r["template"]: r["action"] for r in template_engine.install_native(dest, update=True)["results"]}
        self.assertEqual(actions["generic-pcb"], "UPDATED")
        self.assertEqual(json.loads(marker.read_text())["kit_version"], template_engine.KIT_VERSION)
