"""Asynchronous subprocess runner based on QProcess for long-running CLI operations."""

import json
import os
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, Signal

from tools.core import kicad_env


class ProcessRunner(QObject):
    """Executes external processes asynchronously without blocking the Qt event loop."""

    started = Signal()
    output_received = Signal(str)
    error_received = Signal(str)
    finished = Signal(int, str, object)  # exit_code, raw_output, parsed_json_or_none
    cancelled = Signal()

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._process = QProcess(self)
        self._process.readyReadStandardOutput.connect(self._on_stdout)
        self._process.readyReadStandardError.connect(self._on_stderr)
        self._process.finished.connect(self._on_finished)
        self._stdout_buffer = []
        self._stderr_buffer = []
        self._json_mode = False
        self._is_cancelled = False

    def is_running(self) -> bool:
        return self._process.state() != QProcess.ProcessState.NotRunning

    def start_command(self, program: str, arguments: List[str], json_mode: bool = False,
                      cwd: Optional[str] = None, extra_env: Optional[Dict[str, str]] = None) -> bool:
        """Start an arbitrary command with explicit arguments (no shell)."""
        if self.is_running():
            return False

        self._stdout_buffer.clear()
        self._stderr_buffer.clear()
        self._json_mode = json_mode
        self._is_cancelled = False

        if cwd:
            self._process.setWorkingDirectory(str(cwd))

        # Inherit full system environment (PATH, HOME, etc.) and inject requirements
        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONIOENCODING", "utf-8")
        env.insert("PYTHONUNBUFFERED", "1")
        if extra_env:
            for k, v in extra_env.items():
                env.insert(k, v)
        self._process.setProcessEnvironment(env)

        self._process.start(program, arguments)
        self.started.emit()
        return True

    def start_kit_command(self, kit_args: List[str], json_mode: bool = False,
                          cwd: Optional[str] = None) -> bool:
        venv_py = Path(__file__).resolve().parents[3] / ".venv" / "bin" / "python"
        python = venv_py if venv_py.is_file() else Path(sys.executable)
        root = Path(__file__).resolve().parents[3]
        args = ["-m", "tools"] + kit_args
        if json_mode and "--json" not in args:
            args.append("--json")

        sys_env = QProcessEnvironment.systemEnvironment()
        current_py_path = sys_env.value("PYTHONPATH", "")
        new_py_path = str(root) + ((":" + current_py_path) if current_py_path else "")
        extra_env = {"PYTHONPATH": new_py_path}

        return self.start_command(str(python), args, json_mode=json_mode, cwd=cwd or str(root), extra_env=extra_env)

    def cancel(self) -> None:
        """Cancel and terminate running process."""
        if not self.is_running():
            return
        self._is_cancelled = True
        self._process.terminate()
        if not self._process.waitForFinished(1000):
            self._process.kill()
        self.cancelled.emit()

    def _on_stdout(self) -> None:
        raw = self._process.readAllStandardOutput().data().decode("utf-8", errors="replace")
        self._stdout_buffer.append(raw)
        self.output_received.emit(raw)

    def _on_stderr(self) -> None:
        raw = self._process.readAllStandardError().data().decode("utf-8", errors="replace")
        self._stderr_buffer.append(raw)
        self.error_received.emit(raw)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        full_stdout = "".join(self._stdout_buffer)
        parsed_json = None
        if self._json_mode:
            try:
                # Find start of JSON object or array if preceded by text
                stripped = full_stdout.strip()
                start_idx = -1
                for i, char in enumerate(stripped):
                    if char in ("{", "["):
                        start_idx = i
                        break
                if start_idx >= 0:
                    parsed_json = json.loads(stripped[start_idx:])
            except Exception:
                parsed_json = None

        self.finished.emit(exit_code, full_stdout, parsed_json)
