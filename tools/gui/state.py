"""Application state and reactive model for the GUI."""

from pathlib import Path
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Signal

from tools.core.common import KitError, project_files
from tools.project import registry


class AppState(QObject):
    """Central reactive application state for the desktop GUI."""

    active_project_changed = Signal(str)
    environment_updated = Signal()

    def __init__(self, initial_project: Optional[str] = None):
        super().__init__()
        self._active_project: Optional[Path] = None
        if initial_project:
            self.set_active_project(initial_project)
        else:
            # Pick first existing project from registry if available
            projects = registry.list_projects()
            existing = [p["path"] for p in projects if p.get("exists")]
            if existing:
                self.set_active_project(existing[0])

    @property
    def active_project(self) -> Optional[Path]:
        return self._active_project

    def set_active_project(self, path: Optional[str]) -> None:
        if not path:
            self._active_project = None
            self.active_project_changed.emit("")
            return

        resolved = Path(path).expanduser().resolve()
        if self._active_project == resolved:
            return

        self._active_project = resolved
        self.active_project_changed.emit(str(resolved))

    def active_project_info(self) -> Dict[str, Any]:
        """Return structured summary for the active project."""
        if not self._active_project or not self._active_project.is_dir():
            return {
                "active": False,
                "name": "(No project selected)",
                "path": "",
                "template": None,
                "pro_file": None,
            }

        name = self._active_project.name
        pro_name = None
        try:
            pro, _, _ = project_files(self._active_project)
            pro_name = pro.name
        except (KitError, OSError):
            pass

        template_id = None
        meta_file = self._active_project / "meta/project.json"
        if meta_file.is_file():
            import json
            try:
                template_id = json.loads(meta_file.read_text()).get("template")
            except (ValueError, OSError):
                pass

        return {
            "active": True,
            "name": name,
            "path": str(self._active_project),
            "template": template_id,
            "pro_file": pro_name,
        }
