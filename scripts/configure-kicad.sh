#!/bin/bash
# Install/refresh the native KiCad user templates.
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)/kit" templates install "$@"
