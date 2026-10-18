"""Plugin discovery, verification, update checks and the offline archive installer."""

import hashlib
import json
from pathlib import Path
import unittest
import zipfile

from kit_test_support import NATIVE, EnvPatch, TempDirTest
from tools.plugins import manager as plugins
from tools.core.common import KitError


def fake_kicad_user(tmp, packages, payloads):
    config, docs = tmp / "cfg", tmp / "docs"
    (config / "10.0").mkdir(parents=True)
    (config / "10.0/installed_packages.json").write_text(json.dumps({"packages": [
        {"package": {"identifier": ident}, "current_version": version} for ident, version in packages.items()]}))
    for ident in payloads:
        (docs / "10.0/3rdparty/plugins" / ident.replace(".", "_")).mkdir(parents=True)
    return {"KICAD_CONFIG_HOME": str(config), "KICAD_DOCUMENTS_HOME": str(docs),
            "KICAD_PCBNEW_PYTHON": str(tmp / "no-python")}


class DiscoveryTests(TempDirTest):
    def test_status_from_pcm_database_and_payload(self):
        env = fake_kicad_user(self.tmp, {"org.openscopeproject.InteractiveHtmlBom": "2.12.0",
                                         "app.freerouting.kicad-plugin": "2.4.1",
                                         "com.github.yaqwsx.kikit": "1.6.0"},
                              ["org.openscopeproject.InteractiveHtmlBom", "com.github.yaqwsx.kikit"])
        with EnvPatch(**env):
            rows = {p["key"]: p for p in plugins.diagnose(report=False)["plugins"]}
        self.assertEqual(rows["interactivehtmlbom"]["status"], "INSTALLED_UNVERIFIED")
        self.assertEqual(rows["interactivehtmlbom"]["pcm_version"], "2.12.0")
        # Database entry without payload is not an installation.
        self.assertEqual(rows["freerouting"]["status"], "NOT_INSTALLED")
        # PCM shim present but backend package not importable.
        self.assertEqual(rows["kikit"]["status"], "SHIM_ONLY")
        self.assertEqual(rows["kibot"]["status"], "NOT_INSTALLED")
        self.assertEqual({r["tier"] for r in rows.values()}, {"required", "recommended", "optional"})

    def test_legacy_database_location_is_noted(self):
        env = fake_kicad_user(self.tmp, {}, [])
        legacy = Path(env["KICAD_DOCUMENTS_HOME"]) / "10.0/3rdparty/installed_packages.json"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_text('{"packages": []}')
        with EnvPatch(**env):
            db = plugins.pcm_database()
        self.assertTrue(any("Stale legacy" in n for n in db["notes"]))

    def test_verify_never_claims_uninstalled_plugin(self):
        with EnvPatch(**fake_kicad_user(self.tmp, {}, [])):
            row = plugins.verify("freerouting")
        self.assertEqual(row["status"], "NOT_INSTALLED")
        self.assertFalse(row["verification"]["verified"])

    def test_catalog_covers_required_and_recommended(self):
        names = {p["name"] for p in plugins.PLUGINS.values()}
        self.assertEqual(names, {"InteractiveHtmlBom", "Freerouting", "KiKit", "KiBuzzard", "Board2Pdf", "KiBot",
                                 "pcb-action-tools", "Round Tracks", "HQ DFM"})
        for entry in plugins.PLUGINS.values():
            for field in ("purpose", "optional_dependencies", "known_limitations", "kicad10", "install"):
                self.assertIn(field, entry, entry["name"])
            # Compatibility is only *declared* by catalog data; VERIFIED needs an invocation.
            self.assertIn(entry["verify"], ("ibom-headless", "freerouting-headless", "kikit-panelize",
                                            "kibot-version", "gui-only"))
        for key, entry in plugins.PLUGINS.items():
            guide = plugins.guide(key)
            self.assertTrue(guide["steps"][-1].startswith("Run: scripts/kit plugins verify"))
            if "pcm" in entry["install"]:
                self.assertIn(entry["pcm_identifier"], " ".join(guide["steps"]))


class UpdateTests(unittest.TestCase):
    def fetcher(self, packages, tamper=False):
        raw = json.dumps({"packages": packages}).encode()
        repo = {"packages": {"url": "https://example.invalid/p.json", "sha256": hashlib.sha256(raw).hexdigest(),
                             "update_time_utc": "now"}}
        return lambda url, **_: json.dumps(repo).encode() if url.endswith("repository.json") else (
            raw + (b" " if tamper else b""))

    def test_compatibility_filter(self):
        v = plugins.latest_compatible
        self.assertEqual(v({"versions": [{"version": "2.12.0", "kicad_version": "6.0", "kicad_version_max": "10"}]})
                         ["version"], "2.12.0")
        self.assertIsNone(v({"versions": [{"version": "1.9.2", "kicad_version": "6.0", "kicad_version_max": "9.0"}]}))
        self.assertIsNone(v({"versions": [{"version": "3", "kicad_version": "11.0"}]}))
        self.assertIsNone(v({"versions": [{"version": "1", "kicad_version": "6.0", "platforms": ["windows"]}]}))
        self.assertIsNone(v({"versions": [{"version": "1", "kicad_version": "6.0", "status": "testing"}]}))
        best = v({"versions": [{"version": "1.2.0", "kicad_version": "6.0"}, {"version": "1.10.0", "kicad_version": "6"}]})
        self.assertEqual(best["version"], "1.10.0")

    def test_update_available_and_integrity(self):
        sandbox = Path(__import__("tempfile").mkdtemp())
        env = fake_kicad_user(sandbox, {"app.freerouting.kicad-plugin": "2.3.0"}, [])
        packages = [{"identifier": "app.freerouting.kicad-plugin",
                     "versions": [{"version": "2.4.1", "kicad_version": "6.0"}]}]
        with EnvPatch(**env):
            result = plugins.check_updates(fetch=self.fetcher(packages))
            rows = {r["name"]: r for r in result["plugins"]}
            self.assertEqual(rows["Freerouting"]["status"], "UPDATE_AVAILABLE")
            self.assertEqual(rows["KiBot"]["status"], "NOT_PCM")
            self.assertEqual(rows["KiKit"]["status"], "NO_COMPATIBLE_RELEASE")
            tampered = plugins.check_updates(fetch=self.fetcher(packages, tamper=True))
            self.assertEqual(tampered["status"], "UNAVAILABLE")

    def test_offline_update_check(self):
        def offline(url, **_):
            raise OSError("network unreachable")

        self.assertEqual(plugins.check_updates(fetch=offline)["status"], "UNAVAILABLE")


class ArchiveInstallTests(TempDirTest):
    def make_zip(self, entries, identifier="app.freerouting.kicad-plugin", versions=None):
        path = self.tmp / "pkg.zip"
        meta = {"identifier": identifier, "type": "plugin",
                "versions": versions or [{"version": "9.9.9", "kicad_version": "6.0"}]}
        with zipfile.ZipFile(path, "w") as z:
            z.writestr("metadata.json", json.dumps(meta))
            for name, data in entries.items():
                z.writestr(name, data)
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def test_installs_once_and_is_idempotent(self):
        archive, digest = self.make_zip({"plugins/__init__.py": "x = 1\n"})
        root = self.tmp / "user"
        first = plugins.install_archive("freerouting", archive, digest, root)
        self.assertEqual(first["status"], "INSTALLED")
        self.assertEqual(plugins.install_archive("freerouting", archive, digest, root)["status"], "ALREADY_INSTALLED")
        (Path(first["path"]) / "__init__.py").write_text("tampered")
        with self.assertRaises(KitError):
            plugins.install_archive("freerouting", archive, digest, root)

    def test_rejects_unsafe_or_mismatched_archives(self):
        root = self.tmp / "user"
        archive, digest = self.make_zip({"plugins/__init__.py": ""})
        with self.assertRaises(KitError):
            plugins.install_archive("freerouting", archive, "0" * 64, root)
        for entries in ({"../evil.py": ""}, {"plugins/__init__.py": "", "bin/tool": ""}, {"plugins/x.py": ""}):
            archive, digest = self.make_zip(entries)
            with self.subTest(entries=list(entries)), self.assertRaises(KitError):
                plugins.install_archive("freerouting", archive, digest, root)
        archive, digest = self.make_zip({"plugins/__init__.py": ""}, versions=[{"version": "1", "kicad_version": "11.0"}])
        with self.assertRaises(KitError):
            plugins.install_archive("freerouting", archive, digest, root)

    def test_pcm_managed_plugin_is_left_alone(self):
        root = self.tmp / "user"
        (root / "3rdparty/plugins/app_freerouting_kicad-plugin").mkdir(parents=True)
        archive, digest = self.make_zip({"plugins/__init__.py": ""})
        self.assertEqual(plugins.install_archive("freerouting", archive, digest, root)["status"], "PCM_MANAGED")


@unittest.skipUnless(NATIVE, "KiCad not available")
class InstalledPluginInvocationTests(unittest.TestCase):
    """Headless invocation of the plugins actually installed on this machine."""

    def check(self, name):
        if plugins.status(name)["status"] == "NOT_INSTALLED":
            self.skipTest("%s not installed on this machine" % name)
        row = plugins.verify(name)
        self.assertEqual(row["status"], "VERIFIED", row["verification"])

    def test_interactive_html_bom(self):
        self.check("interactivehtmlbom")

    def test_freerouting(self):
        self.check("freerouting")

    def test_kikit(self):
        self.check("kikit")


if __name__ == "__main__":
    unittest.main()
