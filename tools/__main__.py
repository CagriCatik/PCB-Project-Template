"""``python -m tools`` runs the kit CLI (what scripts/kit does)."""

import sys

from tools.cli.main import main

sys.exit(main())
