"""Desktop GUI entrypoint."""

import sys
from typing import List, Optional

from tools.gui.application import create_qapplication
from tools.gui.main_window import MainWindow
from tools.gui.state import AppState


def main(argv: Optional[List[str]] = None, project: Optional[str] = None, offscreen: bool = False) -> int:
    """Launch the PCB-Project-Template desktop GUI."""
    app = create_qapplication(argv=argv, offscreen=offscreen)
    state = AppState(initial_project=project)
    window = MainWindow(state)

    if not offscreen and sys.platform != "darwin" or "offscreen" not in app.platformName():
        window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
