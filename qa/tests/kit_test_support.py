"""Shared test isolation: no test writes to the real kit state or KiCad user dirs."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.core import kicad_env  # noqa: E402

FIXTURES = ROOT / "qa/fixtures"
FIXTURE = FIXTURES / "divider"
_SANDBOX = None


def sandbox():
    """Process-wide temp dirs for kit state and KiCad user templates."""
    global _SANDBOX
    if _SANDBOX is None:
        _SANDBOX = Path(tempfile.mkdtemp(prefix="kit tests "))
        os.environ["KICAD_KIT_HOME"] = str(_SANDBOX / "kit home")
        os.environ["KICAD_USER_TEMPLATE_DIR"] = str(_SANDBOX / "kicad templates")
    return _SANDBOX


def native_kicad():
    """True when the pinned KiCad is installed and native tests are not disabled."""
    if os.environ.get("KICAD_NATIVE_TESTS") == "0":
        return False
    cli = kicad_env.kicad_cli_path()
    if not cli:
        return False
    try:
        out = subprocess.run([str(cli), "version"], capture_output=True, text=True, timeout=60).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return False
    return out == kicad_env.KICAD_VERSION and kicad_env.bundled_python() is not None


NATIVE = native_kicad()
requires_kicad = unittest.skipUnless(NATIVE, "KiCad %s not available (or KICAD_NATIVE_TESTS=0)" % kicad_env.KICAD_VERSION)


def has_tools(*names):
    return all(shutil.which(n) for n in names)


class EnvPatch:
    """Temporarily set/unset environment variables."""

    def __init__(self, **values):
        self.values, self.saved = values, {}

    def __enter__(self):
        for key, value in self.values.items():
            self.saved[key] = os.environ.get(key)
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = str(value)
        return self

    def __exit__(self, *exc):
        for key, value in self.saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TempDirTest(unittest.TestCase):
    """Each test gets a fresh directory whose path contains spaces."""

    def setUp(self):
        sandbox()
        self._tmp = tempfile.TemporaryDirectory(prefix="kit case ", dir=sandbox())
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def fixture_copy(self, name="fixture board", source=None):
        target = self.tmp / name
        shutil.copytree(source or FIXTURE, target)
        return target


sandbox()
