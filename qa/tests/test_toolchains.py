"""Missing or wrong toolchains fail with specific, documented exit codes."""

import json
import os
import stat
import unittest

from kit_test_support import NATIVE, EnvPatch, TempDirTest, has_tools, requires_kicad
from tools.quality import firmware
from tools.project import templates as template_engine
from tools.core.common import KitError
from tools.kicad.cli import KiCadCLI


def fake_cli(folder, version):
    path = folder / "kicad-cli"
    path.write_text("#!/bin/sh\nif [ \"$1\" = version ]; then echo %s; exit 0; fi\nexit 1\n" % version)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class KiCadToolchainTests(TempDirTest):
    def test_missing_cli_exit_10(self):
        with EnvPatch(KICAD_CLI=str(self.tmp / "absent/kicad-cli")):
            with self.assertRaises(KitError) as ctx:
                KiCadCLI()
        self.assertEqual(ctx.exception.exit_code, 10)

    def test_wrong_version_exit_11(self):
        for version in ("9.0.4", "10.0.6", "11.0.0", "10.99.0-nightly"):
            with self.subTest(version=version), EnvPatch(KICAD_CLI=str(fake_cli(self.tmp, version))):
                with self.assertRaises(KitError) as ctx:
                    KiCadCLI()
                self.assertEqual(ctx.exception.exit_code, 11)

    def test_cli_entrypoint_reports_missing_kicad(self):
        from tools.cli.main import main

        with EnvPatch(KICAD_CLI=str(self.tmp / "none")):
            self.assertEqual(main(["cli", "capabilities"]), 10)
            self.assertEqual(main(["verify", str(self.tmp)]), 12)  # no project here either

    def test_project_creation_does_not_need_kicad_for_blank_templates(self):
        with EnvPatch(KICAD_CLI=str(self.tmp / "none"), KICAD_APP=str(self.tmp / "no.app")):
            path, _ = template_engine.create("generic-pcb", self.tmp / "p", "p", register=False)
            self.assertTrue((path / "p.kicad_pcb").is_file())
            with self.assertRaises(KitError) as ctx:
                template_engine.create("arduino-shield", self.tmp / "a", "a", register=False)
            self.assertEqual(ctx.exception.exit_code, 10)
            self.assertFalse((self.tmp / "a").exists())

    @requires_kicad
    def test_undiscovered_command_or_flag_is_refused(self):
        cli = KiCadCLI()
        self.assertTrue(cli.supports("pcb", "drc", option="--schematic-parity"))
        self.assertFalse(cli.supports("pcb", "export", "nonexistent"))
        with self.assertRaises(KitError) as ctx:
            cli.command(("pcb", "export", "step"), ["--invented-flag", "x.kicad_pcb"])
        self.assertEqual(ctx.exception.exit_code, 15)
        caps = cli.capabilities()
        for needed in ("sch erc", "pcb drc", "sch export bom", "pcb export gerbers", "pcb export drill",
                       "pcb export pos", "pcb export step", "sch export pdf", "pcb export pdf"):
            self.assertIn(needed, caps)


class FirmwareToolchainTests(TempDirTest):
    def test_generic_project_has_no_firmware_target(self):
        path, _ = template_engine.create("generic-pcb", self.tmp / "g", "g", register=False)
        with self.assertRaises(KitError) as ctx:
            firmware.build(path, "host")
        self.assertEqual(ctx.exception.exit_code, 17)

    def test_missing_compiler_reported_not_faked(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "s", "s", register=False)
        # Isolate HOME and ARM_GNU_TOOLCHAIN_BIN too: the toolchain is also searched there.
        with EnvPatch(PATH=str(self.tmp / "empty-bin"), HOME=str(self.tmp / "home"), ARM_GNU_TOOLCHAIN_BIN=None):
            with self.assertRaises(KitError) as ctx:
                firmware.build(path, "stm32")
        self.assertEqual(ctx.exception.exit_code, 17)
        self.assertIn("arm-none-eabi-gcc", str(ctx.exception))
        report = (path / "qa/generated/firmware/stm32.json").read_text()
        self.assertIn("MISSING_TOOLCHAIN", report)

    def test_unknown_target(self):
        with self.assertRaises(KitError):
            firmware.build(self.tmp, "esp32")

    def test_toolchain_inventory_lists_every_tool(self):
        tools = firmware.toolchains()
        for name in ("cmake", "ctest", "cc", "arm-none-eabi-gcc", "pio"):
            self.assertIn(name, tools)


def fake_gcc(bin_dir):
    bin_dir.mkdir(parents=True)
    gcc = bin_dir / "arm-none-eabi-gcc"
    gcc.write_text("#!/bin/sh\necho 'arm-none-eabi-gcc (fake for tests) 0.0'\n")
    gcc.chmod(gcc.stat().st_mode | stat.S_IXUSR)
    return gcc


class ArmToolchainDiscoveryTests(TempDirTest):
    def test_configured_path_wins_and_invalid_path_is_reported(self):
        good = self.tmp / "custom arm/bin"
        fake_gcc(good)
        with EnvPatch(ARM_GNU_TOOLCHAIN_BIN=str(good)):
            self.assertEqual(firmware.arm_toolchain(), (good, "ARM_GNU_TOOLCHAIN_BIN"))
        with EnvPatch(ARM_GNU_TOOLCHAIN_BIN=str(self.tmp / "nowhere")):
            found, reason = firmware.arm_toolchain()
        self.assertIsNone(found)
        self.assertIn("does not contain arm-none-eabi-gcc", reason)

    def test_standard_location_picks_newest_version_without_touching_path(self):
        home = self.tmp / "home"
        fake_gcc(home / "Tools/arm-gnu/arm-gnu-toolchain-14.2.rel1/bin")
        newest = home / "Tools/arm-gnu/arm-gnu-toolchain-15.3.rel2/bin"
        fake_gcc(newest)
        with EnvPatch(HOME=str(home), PATH="/usr/bin:/bin", ARM_GNU_TOOLCHAIN_BIN=None):
            found, source = firmware.arm_toolchain()
            self.assertEqual((found, source), (newest, "standard location"))
            self.assertEqual(os.environ["PATH"], "/usr/bin:/bin")
            env = firmware.stm32_environment()
        self.assertEqual(env["arm_gnu_toolchain"]["bin"], str(newest))
        self.assertIn("fake", env["arm_gnu_toolchain"]["version"])
        self.assertIn("optional", env["stm32cubemx"]["note"])

    def test_pcb_only_projects_never_need_stm32_tools(self):
        path, _ = template_engine.create("generic-pcb", self.tmp / "pcb only", "pcb only", register=False)
        with EnvPatch(HOME=str(self.tmp / "empty home"), ARM_GNU_TOOLCHAIN_BIN=None):
            from tools.quality.verification import load_config

            self.assertEqual(load_config(path)["gates"]["firmware"], "disabled")


STAND_IN_PACKAGE = """# Stand-in reproducing the structure of STM32CubeMX's generated cmake/stm32cubemx
# package (CubeMX 6.18): sources are added to ${CMAKE_PROJECT_NAME}. Wiring test only.
cmake_minimum_required(VERSION 3.22)
add_library(stm32cubemx INTERFACE)
target_include_directories(stm32cubemx INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/../../Inc)
target_sources(${CMAKE_PROJECT_NAME} PRIVATE ${CMAKE_CURRENT_SOURCE_DIR}/../../Src/main.c)
"""
STAND_IN_TOOLCHAIN = 'set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)\n' \
    'set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -T \\"${CMAKE_SOURCE_DIR}/STAND_IN.ld\\"")\n'


class Stm32CMakeWiringTests(TempDirTest):
    """Regression for the template's CubeMX integration (configure step only, host compiler)."""

    def setUp(self):
        super().setUp()
        if not has_tools("cmake", "cc"):
            self.skipTest("cmake/cc not installed")

    def test_generated_package_and_linker_script_are_wired_correctly(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "wiring", "wiring", register=False)
        cube = path / "firmware/bsp/stm32/cubemx"
        (cube / "cmake/stm32cubemx").mkdir(parents=True)
        (cube / "cmake/stm32cubemx/CMakeLists.txt").write_text(STAND_IN_PACKAGE)
        (cube / "cmake/gcc-arm-none-eabi.cmake").write_text(STAND_IN_TOOLCHAIN)
        (cube / "Inc").mkdir()
        (cube / "Inc/main.h").write_text("#define MY_LED_Pin 1\n#define MY_LED_GPIO_Port 0\n")
        (cube / "Src").mkdir()
        (cube / "Src/main.c").write_text("int main(void) { return 0; }\n")
        from tools.core.common import run

        record = run(["cmake", "--preset", "stm32-debug", "-DFW_STATUS_LED=MY_LED"], cwd=path / "firmware")
        self.assertEqual(record["exit_code"], 0, record["stderr"][-2000:])
        build = path / "firmware/build/stm32-debug"
        link = (build / "CMakeFiles/firmware.dir/link.txt").read_text()
        self.assertIn("bsp/stm32/cubemx/STAND_IN.ld", link)  # linker script resolved inside the CubeMX dir
        flags = (build / "CMakeFiles/firmware.dir/flags.make").read_text()
        self.assertIn("BSP_STATUS_LED=MY_LED", flags)

    def test_missing_cubemx_output_gives_actionable_error(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "no cubemx", "nc", register=False)
        from tools.core.common import run

        record = run(["cmake", "-S", path / "firmware", "-B", self.tmp / "b", "-DFW_TARGET=stm32"])
        self.assertNotEqual(record["exit_code"], 0)
        self.assertIn("STM32CubeMX project missing", record["stderr"])


@unittest.skipUnless(os.environ.get("KIT_STM32_CUBEMX_SOURCE"),
                     "set KIT_STM32_CUBEMX_SOURCE to a CubeMX CMake project (USER CODE without external "
                     "references) for the real STM32 cross-build")
class Stm32CrossBuildTests(TempDirTest):
    def test_real_cross_build_and_relocation(self):
        import shutil

        if firmware.arm_toolchain()[0] is None:
            self.skipTest("Arm GNU toolchain not found")
        path, _ = template_engine.create("stm32-embedded", self.tmp / "real stm32 ✓", "real", register=False)
        shutil.copytree(os.environ["KIT_STM32_CUBEMX_SOURCE"], path / "firmware/bsp/stm32/cubemx",
                        ignore=shutil.ignore_patterns("build"), dirs_exist_ok=True)
        label = os.environ.get("KIT_STM32_STATUS_LED", "STATUS_LED")
        presets = path / "firmware/CMakePresets.json"
        data = json.loads(presets.read_text())
        next(c for c in data["configurePresets"] if c["name"] == "stm32-debug")["cacheVariables"][
            "FW_STATUS_LED"] = label
        presets.write_text(json.dumps(data))
        result = firmware.build(path, "stm32")
        self.assertEqual(result["status"], "PASS", result["commands"][-1]["stderr"][-2000:])
        art = result["artifact"]
        self.assertEqual(art["elf_header"]["Machine"], "ARM")
        self.assertEqual(art["elf_header"]["Class"], "ELF32")
        self.assertTrue(art["memory_usage"])
        moved = self.tmp / "verschoben 移動"
        shutil.move(str(path), str(moved))
        again = firmware.build(moved, "stm32")
        self.assertEqual(again["status"], "PASS")
        self.assertTrue(again.get("reconfigured_after_relocation"))


class FirmwareBuildTests(TempDirTest):
    """Real host builds: module-level and hardware-interface edge-case tests."""

    def setUp(self):
        super().setUp()
        if not has_tools("cmake", "ctest", "cc"):
            self.skipTest("cmake/ctest/cc not installed")

    def test_stm32_template_host_tests_pass(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "stm32 fw", "stm32 fw", register=False)
        result = firmware.build(path, "host")
        self.assertEqual(result["status"], "PASS", result["commands"][-1]["stdout"][-2000:])
        self.assertIn("heartbeat", result["commands"][-1]["stdout"])

    def test_arduino_template_host_tests_pass(self):
        if not NATIVE:
            self.skipTest("arduino-shield needs the KiCad bundle")
        path, _ = template_engine.create("arduino-shield", self.tmp / "uno fw", "uno fw", register=False)
        self.assertTrue((path / "firmware/platformio.ini").is_file())
        self.assertEqual(firmware.build(path, "host")["status"], "PASS")

    def test_host_build_survives_project_relocation(self):
        import shutil

        path, _ = template_engine.create("stm32-embedded", self.tmp / "before move", "mv", register=False)
        self.assertEqual(firmware.build(path, "host")["status"], "PASS")
        moved = self.tmp / "nach dem Umzug – ü"
        shutil.move(str(path), str(moved))
        result = firmware.build(moved, "host")
        self.assertEqual(result["status"], "PASS", result["commands"][-1]["stderr"][-1500:])
        self.assertTrue(result.get("reconfigured_after_relocation"))
        self.assertFalse(firmware.build(moved, "host").get("reconfigured_after_relocation"))

    def test_failing_unit_test_is_detected(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "broken", "broken", register=False)
        src = path / "firmware/app/src/heartbeat.c"
        # Inject a real defect: toggling at a quarter instead of half the period.
        src.write_text(src.read_text().replace("active_period(hb) / 2u", "active_period(hb) / 4u"))
        result = firmware.build(path, "host")
        self.assertEqual(result["status"], "FAIL")
        self.assertNotEqual(result["commands"][-1]["exit_code"], 0)

    def test_compiler_warnings_are_errors(self):
        path, _ = template_engine.create("stm32-embedded", self.tmp / "warn", "warn", register=False)
        src = path / "firmware/app/src/heartbeat.c"
        src.write_text(src.read_text() + "\nstatic int unused_function(void) { return 1; }\n")
        self.assertEqual(firmware.build(path, "host")["status"], "FAIL")


if __name__ == "__main__":
    import unittest

    unittest.main()
