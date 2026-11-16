"""Unique, fail-marked evidence directories for read-only calculations/checks."""
from pathlib import Path
import tempfile

from tools.core.common import KitError, now, write_json


def recorded_run(project, category, operation):
    root = Path(project).resolve()
    if not root.is_dir():
        raise KitError('Project directory does not exist: ' + str(root))
    parent = root / 'qa/generated' / category
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix='run-', dir=parent))
    try:
        result = operation()
        result['directory'] = str(folder)
        write_json(folder / 'result.json', result)
        return result
    except Exception as exc:
        write_json(folder / 'result.json', {'status': 'FAILED', 'created': now(),
                                         'directory': str(folder), 'error': str(exc)})
        if isinstance(exc, KitError):
            raise KitError('%s (failed run: %s)' % (exc, folder), exc.exit_code) from exc
        raise
