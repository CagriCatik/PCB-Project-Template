"""IPC diagnostics: configuration, failure classification, safe enabling, live probe."""

import json
import unittest

from kit_test_support import EnvPatch, TempDirTest
from tools.kicad import ipc


def config_home(tmp, api):
    base = tmp / "Preferences kicad"
    (base / "10.0").mkdir(parents=True)
    settings = {"api": api, "appearance": {"toolbar_icon_size": 24}, "environment": {"vars": {}}}
    (base / "10.0/kicad_common.json").write_text(json.dumps(settings, indent=4))
    return base


class IpcConfigTests(TempDirTest):
    def test_reads_disabled_server_setting(self):
        with EnvPatch(KICAD_CONFIG_HOME=str(config_home(self.tmp, {"enable_server": False}))):
            config = ipc.api_config()
        self.assertTrue(config["config_exists"])
        self.assertIs(config["enable_server"], False)

    def test_missing_config(self):
        with EnvPatch(KICAD_CONFIG_HOME=str(self.tmp / "nowhere")):
            self.assertFalse(ipc.api_config()["config_exists"])
            with self.assertRaises(Exception):
                ipc.enable_server(apply=True)

    def test_enable_refused_while_kicad_runs(self):
        base = config_home(self.tmp, {"enable_server": False})
        before = (base / "10.0/kicad_common.json").read_text()
        with EnvPatch(KICAD_CONFIG_HOME=str(base), KICAD_KIT_ASSUME_RUNNING="1"):
            with self.assertRaises(Exception) as ctx:
                ipc.enable_server(apply=True)
        self.assertEqual(ctx.exception.exit_code, 16)
        self.assertEqual((base / "10.0/kicad_common.json").read_text(), before)

    def test_enable_dry_run_then_apply_with_backup(self):
        base = config_home(self.tmp, {"enable_server": False, "interpreter_path": "/x/python3"})
        cfg = base / "10.0/kicad_common.json"
        original = cfg.read_text()
        with EnvPatch(KICAD_CONFIG_HOME=str(base), KICAD_KIT_ASSUME_RUNNING="0"):
            dry = ipc.enable_server(apply=False)
            self.assertEqual(dry["status"], "DRY_RUN")
            self.assertEqual(cfg.read_text(), original)
            done = ipc.enable_server(apply=True)
            self.assertEqual(done["status"], "ENABLED")
            data = json.loads(cfg.read_text())
            self.assertIs(data["api"]["enable_server"], True)
            self.assertEqual(data["api"]["interpreter_path"], "/x/python3")  # other settings preserved
            self.assertEqual(data["appearance"]["toolbar_icon_size"], 24)
            from pathlib import Path

            self.assertEqual(Path(done["backup"]).read_text(), original)
            self.assertEqual(ipc.enable_server(apply=True)["status"], "ALREADY_ENABLED")


class IpcFailureTests(TempDirTest):
    def test_unreachable_socket_is_classified_quickly(self):
        result = ipc.probe("ipc://%s/no/such/api.sock" % self.tmp, timeout_ms=1000, budget_s=30)
        self.assertFalse(result["reachable"])
        self.assertIn(result["error_class"], ("connection_failed", "client_missing", "timeout"))

    def test_missing_client_is_reported(self):
        result = ipc.probe(None, python="/usr/bin/false")
        self.assertFalse(result["reachable"])
        self.assertEqual(result["error_class"], "probe_failed")

    def test_diagnosis_explains_disabled_server(self):
        base = config_home(self.tmp, {"enable_server": False})
        with EnvPatch(KICAD_CONFIG_HOME=str(base), KICAD_KIT_ASSUME_RUNNING="1",
                      KICAD_API_SOCKET="ipc://%s/absent.sock" % self.tmp):
            result = ipc.diagnose(timeout_ms=1000)
        self.assertEqual(result["status"], "UNAVAILABLE")
        self.assertTrue(any("enable_server=False" in c for c in result["causes"]), result["causes"])
        self.assertEqual(result["sockets"][0]["source"], "KICAD_API_SOCKET")

    def test_cli_exit_code_when_unavailable(self):
        from tools.cli.main import main

        with EnvPatch(KICAD_CONFIG_HOME=str(config_home(self.tmp, {"enable_server": False})),
                      KICAD_API_SOCKET="ipc://%s/absent.sock" % self.tmp):
            self.assertEqual(main(["ipc", "status", "--timeout-ms", "500"]), 3)


class IpcLiveTests(unittest.TestCase):
    """Runs only when a KiCad instance with the API server is actually reachable."""

    def test_live_connection_and_queries(self):
        result = ipc.diagnose()
        if not result["reachable"]:
            self.skipTest("no reachable KiCad IPC server: " + "; ".join(result["causes"]))
        conn = result["connection"]
        self.assertTrue(conn["versions"]["server"].startswith("10.0"))
        self.assertIn("documents", conn)


if __name__ == "__main__":
    unittest.main()
