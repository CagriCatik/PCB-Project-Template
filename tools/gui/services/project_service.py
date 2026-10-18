"""Synchronous application service wrapping core project, environment, and registry operations."""

import json
import sys
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from tools.core import kicad_env
from tools.core.common import KitError, project_files
from tools.environment import installer
from tools.project import profiles, registry, templates
from tools.release import exports

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.-]*$")


class ProjectService:
    """Service providing access to existing backend operations."""

    @staticmethod
    def get_environment_info() -> Dict[str, Any]:
        """Return diagnostic information about the local development environment."""
        cli = kicad_env.kicad_cli_path()
        app = kicad_env.kicad_app()
        try:
            from tools.kicad.cli import KiCadCLI
            version = KiCadCLI().version
        except Exception:
            version = None
        venv = Path(__file__).resolve().parents[3] / ".venv" / "bin" / "python"
        kit_python = str(venv) if venv.is_file() else sys.executable
        is_running = bool(kicad_env.running_kicad())

        return {
            "kicad_version": version,
            "kicad_cli": str(cli) if cli else None,
            "kicad_app": str(app) if app else None,
            "kicad_running": is_running,
            "kit_python": kit_python,
            "template_dir": str(kicad_env.user_template_dir()),
        }

    @staticmethod
    def list_projects() -> List[Dict[str, Any]]:
        """List registered projects."""
        return registry.list_projects()

    @staticmethod
    def register_project(path: str) -> None:
        """Register a project path."""
        p = Path(path).expanduser().resolve()
        project_files(p)  # validates presence of .kicad_pro/.kicad_sch/.kicad_pcb
        registry.register_project(p)

    @staticmethod
    def forget_project(path: str) -> None:
        """Remove a project from the registry."""
        registry.forget_project(path)

    @staticmethod
    def get_templates() -> Dict[str, Dict[str, Any]]:
        """Return available templates and their properties."""
        return templates.templates()

    @staticmethod
    def get_profiles() -> Dict[str, Dict[str, Any]]:
        """Return available board profiles."""
        return profiles.profiles()

    @staticmethod
    def validate_new_project_input(name: str, dest: str) -> Tuple[bool, str]:
        """Validate proposed project name and destination directory."""
        if not name:
            return False, "Project name cannot be empty."
        try:
            templates.validate_name(name)
        except KitError as exc:
            return False, str(exc)

        if not dest.strip():
            return False, "Destination directory cannot be empty."

        dest_path = Path(dest).expanduser().resolve()
        if dest_path.is_file():
            return False, f"Destination is an existing file: {dest_path}"
        if dest_path.is_dir() and any(dest_path.iterdir()):
            return False, f"Destination exists and is not an empty directory: {dest_path}"

        return True, ""

    @staticmethod
    def create_project(template_id: str, dest: str, name: str, git: bool = False,
                       register: bool = True, profile: Optional[str] = None) -> Tuple[Path, Dict[str, Any]]:
        """Create a new project from a template using the template engine."""
        return templates.create(
            template_id=template_id,
            dest=dest,
            name=name,
            git=git,
            register=register,
            profile_id=profile,
        )

    @staticmethod
    def open_in_kicad(project_path: str) -> Dict[str, Any]:
        """Open the project in KiCad."""
        return registry.open_project(project_path, vscode=False)

    @staticmethod
    def open_in_vscode(project_path: str) -> Dict[str, Any]:
        """Open the project in VS Code."""
        return registry.open_project(project_path, vscode=True)

    @staticmethod
    def get_release_status(project_path: str) -> List[Dict[str, Any]]:
        """Get manufacturing releases status."""
        p = Path(project_path).expanduser().resolve()
        if not p.is_dir():
            return []
        try:
            return exports.release_status(p)
        except Exception:
            return []
